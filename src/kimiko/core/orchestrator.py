"""Request Orchestrator — the central pipeline manager.

Every request flows through here. Corrected pipeline (Fix #1):
  Request → Intent → Retrieval → Context Ranking → Context Builder → Model Router → LLM → Stream
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from kimiko.agents.engine import AgentEngine
from kimiko.core.context_builder import ContextBuilder
from kimiko.core.intent import IntentClassifier
from kimiko.core.model_router import ModelRouter
from kimiko.core.observability import LLM_ERRORS, LLM_GENERATION_DURATION
from kimiko.core.retrieval_engine import RetrievalEngine
from kimiko.core.streaming import StreamingEngine
from kimiko.core.token_manager import TokenManager
from kimiko.memory.document_engine import DocumentEngine
from kimiko.memory.manager import MemoryManager
from kimiko.plugins.manager import PluginManager
from kimiko.services.vision_engine import VisionEngine
from kimiko.models.schemas import (
    ChatRequest,
    ChatResponse,
    Intent,
    Message,
    Role,
    TokenUsage,
)
from kimiko.services.llm import LLMServiceError, get_llm_service
from kimiko.services.model_scheduler import ModelScheduler
from kimiko.tools.core import CalculatorTool, FileSystemTool
from kimiko.tools.registry import ToolRegistry
from kimiko.tools.search import WebSearchTool
from kimiko.tools.datetime_tool import DateTimeTool
from kimiko.tools.terminal import TerminalTool
from kimiko.tools.os_filesystem import OSFileSystemTool

# OS Agent Identity
OS_USER_ID = "00000000-0000-0000-0000-000000000001"

logger = structlog.get_logger(__name__)


class RequestOrchestrator:
    """Central pipeline manager — coordinates all components for each request."""

    def __init__(self) -> None:
        self.memory = MemoryManager()
        self.intent_classifier = IntentClassifier()
        self.token_manager = TokenManager()
        self.context_builder = ContextBuilder(self.token_manager)
        self.retrieval_engine = RetrievalEngine(self.memory)
        self.model_router = ModelRouter()
        self.streaming_engine = StreamingEngine()
        
        # New Phase 2 Engines (Fix #1 review round 3)
        self.document_engine = DocumentEngine(self.memory.semantic)
        
        self.tool_registry = ToolRegistry()
        self.tool_registry.register(CalculatorTool())
        self.tool_registry.register(FileSystemTool(allowed_paths=["./"]))
        self.tool_registry.register(WebSearchTool())
        self.tool_registry.register(DateTimeTool())
        self.tool_registry.register(TerminalTool())
        self.tool_registry.register(OSFileSystemTool())
        
        # Load external plugins dynammically from src/kimiko/plugins/installed/
        self.plugin_manager = PluginManager(self.tool_registry)
        loaded_plugins = self.plugin_manager.load_plugins()
        logger.info("plugins_loaded", count=loaded_plugins)
        
        self.agent_engine = AgentEngine(self.tool_registry)
        self.vision_engine = VisionEngine()
        
        self.scheduler = ModelScheduler()

    async def _validate_citations(self, response: str, results: list[Any]) -> str:
        """Heuristic to ensure citations match retrieved sources."""
        import re
        valid_sources = {r.source.lower() for r in results}
        # Add common aliases
        if "user_facts" in valid_sources: valid_sources.add("user facts")
        if "short_term" in valid_sources: valid_sources.add("memory")
        if "long_term" in valid_sources: valid_sources.add("long-term memory")
        
        # Find all [Source: ...] patterns
        citations = re.findall(r"\[Source:\s*(.*?)\]", response)
        for c in citations:
            if c.lower() not in valid_sources:
                # Meta-hallucination detected: model cited something not in context
                logger.warning("fabricated_citation_detected", source=c)
                response = response.replace(f"[Source: {c}]", "")
        
        return response

    async def _verify_grounding(self, response: str, results: list[Any], model: str) -> bool:
        """Second-pass verification: Does the context support the answer?"""
        if not results: return False
        
        context_text = "\n".join([f"- {r.text}" for r in results])
        verification_prompt = (
            f"Context:\n{context_text}\n\n"
            f"Candidate Answer:\n{response}\n\n"
            "Task: Verify if the 'Candidate Answer' is fully supported by the 'Context'.\n"
            "If it is supported, return exactly: SUPPORTED\n"
            "If it is NOT supported or contains extra info, return exactly: UNSUPPORTED"
        )
        
        try:
            llm = get_llm_service()
            v_result = await llm.generate(
                model=model,
                prompt=verification_prompt,
                temperature=0.0, # Purely deterministic
                max_tokens=10
            )
            v_text = v_result.get("response", "").strip().upper()
            return "SUPPORTED" in v_text
        except Exception:
            return True # Fallback to true if verifier fails

    @staticmethod
    def _passes_dynamic_threshold(item: Any, default_threshold: float) -> bool:
        """Source-aware query-time filtering."""
        if item.source in {"long_term", "fact_store"}:
            return item.score >= 0.45
        return item.score >= default_threshold

    async def process(
        self,
        request: ChatRequest,
        db: AsyncSession,
        session_id: str | None = None,
        request_id: str | None = None,
    ) -> ChatResponse:
        """Process a chat request, routing to Agent if it's an OS request."""
        request_id = request_id or str(uuid.uuid4())[:8]
        user_message = request.message
        session_id = request.session_id or request_id

        # ── OS AGENT PATH ──
        if request.user_id == OS_USER_ID:
            logger.info("routing_to_agent_engine", session_id=session_id)
            await self.memory.add_message(
                session_id,
                Message(role=Role.USER, content=user_message),
                request_id=request_id,
                user_id=request.user_id
            )
            history = await self.memory.get_conversation(session_id)
            from langchain_core.messages import HumanMessage, AIMessage
            lc_history = []
            for m in history[:-1]:
                if m.role == Role.USER: lc_history.append(HumanMessage(content=m.content))
                else: lc_history.append(AIMessage(content=m.content))

            response_text, trace = await self.agent_engine.run(
                goal=user_message,
                history=lc_history,
                images=request.images
            )
            await self.memory.add_message(
                session_id,
                Message(role=Role.ASSISTANT, content=response_text),
                request_id=request_id,
                user_id=request.user_id
            )
            return ChatResponse(
                id=request_id,
                session_id=session_id,
                message=Message(role=Role.ASSISTANT, content=response_text),
                model="agent-orchestrated",
                intent="OS_AGENT",
                usage=TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
            )

        # ── STANDARD CHAT PATH ──
        start_time = time.time()
        await self.memory.add_message(
            session_id,
            Message(role=Role.USER, content=user_message),
            request_id=request_id,
            user_id=request.user_id
        )

        intent_result = self.intent_classifier.classify(user_message)
        model = await self.model_router.route(
            intent=intent_result.intent,
            preferred_model=request.model,
        )

        is_complex = len(user_message) > 60 or "?" in user_message
        dynamic_threshold = 0.75 if is_complex else 0.60
        
        retrieval_results = await self.retrieval_engine.retrieve(
            query=user_message,
            session_id=session_id,
            user_id=request.user_id,
            db=db,
            top_k=5, 
        )
        retrieval_results = [
            r for r in retrieval_results if self._passes_dynamic_threshold(r, dynamic_threshold)
        ]

        conversation_history = await self.memory.get_conversation(session_id)
        conversation_summary = await self.memory.get_conversation_summary(session_id)

        prompt_data = self.context_builder.build(
            user_message=user_message,
            model=model,
            conversation_history=conversation_history[:-1],
            retrieval_results=retrieval_results,
            conversation_summary=conversation_summary,
        )

        try:
            if request.images:
                await self.scheduler.schedule_vision(model)
            else:
                await self.scheduler.schedule_chat(model)

            with LLM_GENERATION_DURATION.labels(model=model).time():
                llm = get_llm_service()
                result = await llm.generate(
                    model=model,
                    prompt=prompt_data["prompt"],
                    system=prompt_data["system"],
                    images=prompt_data.get("images"),
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                )
        except LLMServiceError as e:
            LLM_ERRORS.labels(model=model, error_type=type(e).__name__).inc()
            logger.error("llm_generation_failed", error=str(e), model=model)
            raise

        response_text = result.get("response", "")
        await self.memory.add_message(
            session_id,
            Message(role=Role.ASSISTANT, content=response_text),
            request_id=request_id,
            user_id=request.user_id
        )

        duration = time.time() - start_time
        logger.info(
            "pipeline_complete",
            request_id=request_id,
            model=model,
            intent=intent_result.intent.value,
            duration=f"{duration:.2f}s",
        )
        
        validated_content = await self._validate_citations(response_text, retrieval_results)
        final_text = validated_content
        if intent_result.intent == Intent.QUESTION and retrieval_results:
            is_supported = await self._verify_grounding(validated_content, retrieval_results, model)
            if not is_supported:
                final_text = "I do not have enough verified information in my memory to answer this question accurately."

        return ChatResponse(
            id=request_id,
            session_id=session_id,
            message=Message(role=Role.ASSISTANT, content=final_text),
            model=model,
            intent=intent_result.intent.value,
            usage=TokenUsage(
                prompt_tokens=result.get("prompt_eval_count", 0),
                completion_tokens=result.get("eval_count", 0),
                total_tokens=result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
            ),
        )

    async def process_stream(
        self,
        request: ChatRequest,
        db: AsyncSession | None = None,
        request_id: str | None = None,
        disconnect_event: asyncio.Event | None = None,
    ) -> AsyncIterator[str]:
        """Process a streaming chat request."""
        request_id = request_id or str(uuid.uuid4())[:8]
        user_message = request.message
        session_id = request.session_id or request_id

        # ── OS AGENT PATH (No streaming for now) ──
        if request.user_id == OS_USER_ID:
            # For simplicity, we wrap the non-streaming agent logic in an iterator
            response = await self.process(request, db, session_id, request_id)
            # Re-format as SSE
            import json
            yield f"data: {json.dumps({'event': 'token', 'data': response.message.content})}\n\n"
            yield f"data: {json.dumps({'event': 'done'})}\n\n"
            return

        # ── STANDARD CHAT PATH ──
        await self.memory.add_message(
            session_id,
            Message(role=Role.USER, content=user_message),
            request_id=request_id,
        )

        intent_result = self.intent_classifier.classify(user_message)
        model = await self.model_router.route(
            intent=intent_result.intent,
            preferred_model=request.model,
        )

        is_complex = len(user_message) > 60 or "?" in user_message
        dynamic_threshold = 0.75 if is_complex else 0.60

        retrieval_results = await self.retrieval_engine.retrieve(
            query=user_message,
            session_id=session_id,
            user_id=request.user_id,
            db=db,
            top_k=5,
        )
        retrieval_results = [
            r for r in retrieval_results if self._passes_dynamic_threshold(r, dynamic_threshold)
        ]

        conversation_history = await self.memory.get_conversation(session_id)
        conversation_summary = await self.memory.get_conversation_summary(session_id)

        prompt_data = self.context_builder.build(
            user_message=user_message,
            model=model,
            conversation_history=conversation_history[:-1],
            retrieval_results=retrieval_results,
            conversation_summary=conversation_summary,
        )

        if request.images:
            await self.scheduler.schedule_vision(model)
        else:
            await self.scheduler.schedule_chat(model)
            
        llm = get_llm_service()
        token_stream = llm.stream(
            model=model,
            prompt=prompt_data["prompt"],
            system=prompt_data["system"],
            images=prompt_data.get("images"),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        collected_tokens: list[str] = []
        async for sse_event in self.streaming_engine.stream_response(
            token_stream, model, check_disconnected=disconnect_event
        ):
            import json
            try:
                data = json.loads(sse_event.replace("data: ", "").strip())
                if data.get("event") == "token":
                    collected_tokens.append(data.get("data", ""))
            except (json.JSONDecodeError, ValueError):
                pass
            yield sse_event

        full_response = "".join(collected_tokens)
        if full_response:
            await self.memory.add_message(
                session_id,
                Message(role=Role.ASSISTANT, content=full_response),
                request_id=request_id,
            )
