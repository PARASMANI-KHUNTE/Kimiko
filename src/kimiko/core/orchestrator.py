"""Request Orchestrator — the central pipeline manager.

Every request flows through here. Corrected pipeline (Fix #1):
  Request → Intent → Retrieval → Context Ranking → Context Builder → Model Router → LLM → Stream
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from kimiko.agents.engine import AgentEngine
from kimiko.config import get_settings
from kimiko.core.context_builder import ContextBuilder
from kimiko.core.intent import IntentClassifier
from kimiko.core.model_router import ModelRouter
from kimiko.core.observability import LLM_ERRORS, LLM_GENERATION_DURATION
from kimiko.core.retrieval_engine import RetrievalEngine
from kimiko.core.streaming import StreamingEngine
from kimiko.core.token_manager import TokenManager
from kimiko.db.bootstrap import resolve_user_id
from kimiko.memory.document_engine import DocumentEngine
from kimiko.memory.manager import MemoryManager
from kimiko.models.schemas import (
    ChatRequest,
    ChatResponse,
    Intent,
    Message,
    Role,
    TokenUsage,
)
from kimiko.plugins.manager import PluginManager
from kimiko.services.llm import get_llm_service
from kimiko.services.model_scheduler import ModelScheduler
from kimiko.services.vision_engine import VisionEngine
from kimiko.tools.automation import AppAutomationTool
from kimiko.tools.core import CalculatorTool, FileSystemTool
from kimiko.tools.datetime_tool import DateTimeTool
from kimiko.tools.os_filesystem import OSFileSystemTool
from kimiko.tools.registry import ToolRegistry
from kimiko.tools.search import WebSearchTool
from kimiko.tools.system_context import SystemContextTool
from kimiko.tools.terminal import TerminalTool

# OS Agent Identity
OS_USER_ID = "00000000-0000-0000-0000-000000000001"

_CITATION_RE = re.compile(r"\[Source:\s*(.*?)\]")
_INVALID_CITATION_RE = re.compile(r"[^a-z0-9\s_-]+")

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
        self.tool_registry.register(SystemContextTool())
        self.tool_registry.register(AppAutomationTool())

        # Load external plugins dynammically from src/kimiko/plugins/installed/
        self.plugin_manager = PluginManager(self.tool_registry)
        loaded_plugins = self.plugin_manager.load_plugins()
        logger.info("plugins_loaded", count=loaded_plugins)

        self.agent_engine = AgentEngine(self.tool_registry)
        self.vision_engine = VisionEngine()

        self.scheduler = ModelScheduler()

    async def _validate_citations(self, response: str, results: list[Any]) -> str:
        """Heuristic to ensure citations match retrieved sources."""
        valid_sources = {r.source.lower() for r in results}
        # Add common aliases
        if "user_facts" in valid_sources:
            valid_sources.add("user facts")
        if "short_term" in valid_sources:
            valid_sources.add("memory")
        if "long_term" in valid_sources:
            valid_sources.add("long-term memory")

        def _replace(match: re.Match[str]) -> str:
            citation = match.group(1)
            if citation.lower().strip() in valid_sources:
                return match.group(0)
            # Meta-hallucination detected: model cited something not in context
            logger.warning("fabricated_citation_detected", source=citation)
            return ""

        # Single regex pass instead of ``findall`` + repeated ``str.replace``.
        return _CITATION_RE.sub(_replace, response)

    @staticmethod
    def _lexical_grounding_score(response: str, results: list[Any]) -> float:
        """Cheap lexical overlap proxy for grounding (no LLM call).

        Returns the fraction of distinctive answer tokens that also appear in
        the retrieved context. Used for observability; not a hard gate.
        """
        if not response or not results:
            return 0.0
        context = " ".join(str(r.text) for r in results).lower()
        context_tokens = {t for t in _INVALID_CITATION_RE.split(context) if len(t) > 3}
        answer_tokens = {
            t for t in _INVALID_CITATION_RE.split(response.lower()) if len(t) > 3
        }
        if not answer_tokens or not context_tokens:
            return 0.0
        return len(answer_tokens & context_tokens) / len(answer_tokens)

    async def _verify_grounding(self, response: str, results: list[Any], model: str) -> bool:
        """Second-pass verification: Does the context support the answer?

        This costs a full extra LLM round-trip, so it is opt-in via
        ``KIMIKO_VERIFY_GROUNDING=true``. The default fast path skips it.
        """
        if not results:
            return False

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
                temperature=0.0,  # Purely deterministic
                max_tokens=10,
            )
            v_text = v_result.get("response", "").strip().upper()
            return "SUPPORTED" in v_text
        except Exception:
            return True  # Fallback to true if verifier fails

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

        # Attribute anonymous web/CLI requests to the seeded local user so
        # memories and extracted facts land in a real ``users`` row.
        request.user_id = resolve_user_id(request.user_id)

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
            from langchain_core.messages import AIMessage, HumanMessage
            lc_history = []
            for m in history[:-1]:
                if m.role == Role.USER:
                    lc_history.append(HumanMessage(content=m.content))
                else:
                    lc_history.append(AIMessage(content=m.content))

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
        is_complex = len(user_message) > 60 or "?" in user_message
        dynamic_threshold = 0.75 if is_complex else 0.60

        # Fetch the summary once and share it with retrieval (saves a Redis GET).
        # Then run retrieval, history, and model routing concurrently: the slow
        # embedding + vector + SQL work overlaps instead of running serially.
        conversation_summary = await self.memory.get_conversation_summary(session_id)
        retrieval_results, conversation_history, model = await asyncio.gather(
            self.retrieval_engine.retrieve(
                query=user_message,
                session_id=session_id,
                user_id=request.user_id,
                db=db,
                top_k=5,
                conversation_summary=conversation_summary,
                include_summary=False,
            ),
            self.memory.get_conversation(session_id),
            self.model_router.route(
                intent=intent_result.intent,
                preferred_model=request.model,
            ),
        )
        retrieval_results = [
            r for r in retrieval_results if self._passes_dynamic_threshold(r, dynamic_threshold)
        ]

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
        except Exception as e:
            from kimiko.services.llm import ModelNotAvailableError
            if isinstance(e, ModelNotAvailableError):
                logger.error("model_not_found", model=model, error=str(e))
                return ChatResponse(
                    id=request_id,
                    session_id=session_id,
                    message=Message(
                        role=Role.ASSISTANT,
                        content=(
                            f"⚠️ Model '{model}' is not available in Ollama. "
                            f"Please run `ollama pull {model}` to use this feature."
                        ),
                    ),
                    model=model,
                    intent=intent_result.intent.value if 'intent_result' in locals() else "UNKNOWN",
                    usage=TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
                )
            LLM_ERRORS.labels(model=model, error_type=type(e).__name__).inc()
            logger.error("llm_generation_failed", error=str(e), model=model)
            raise

        response_text = result.get("response", "")
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
            # Cheap lexical check for observability (no extra LLM call).
            overlap = self._lexical_grounding_score(validated_content, retrieval_results)
            if overlap < 0.1:
                logger.warning(
                    "low_grounding_overlap",
                    request_id=request_id,
                    overlap=round(overlap, 3),
                )
            # Opt-in strict verification; off by default because it doubles latency.
            if get_settings().verify_grounding:
                is_supported = await self._verify_grounding(
                    validated_content, retrieval_results, model
                )
                if not is_supported:
                    final_text = (
                        "I do not have enough verified information in my memory "
                        "to answer this question accurately."
                    )

        # Persist the final answer (after citation cleanup / grounding), not the draft.
        await self.memory.add_message(
            session_id,
            Message(role=Role.ASSISTANT, content=final_text),
            request_id=request_id,
            user_id=request.user_id
        )

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
    ) -> AsyncIterator[dict[str, str]]:
        """Process a streaming chat request."""
        try:
            request_id = request_id or str(uuid.uuid4())[:8]
            user_message = request.message
            session_id = request.session_id or request_id

            # Keep streaming attribution consistent with the non-streaming path.
            request.user_id = resolve_user_id(request.user_id)

            # ── OS AGENT PATH (Experimental Streaming) ──
            if request.user_id == OS_USER_ID:
                yield {
                    "data": json.dumps(
                        {"event": "thought", "data": "Thinking about your request..."}
                    )
                }

                # Persist the user turn before loading history (matches the
                # non-streaming path and keeps history ordering correct).
                await self.memory.add_message(
                    session_id,
                    Message(role=Role.USER, content=user_message),
                    request_id=request_id,
                    user_id=request.user_id,
                )
                history = await self.memory.get_conversation(session_id)
                from langchain_core.messages import AIMessage, HumanMessage
                lc_history = []
                for m in history[:-1]:
                    if m.role == Role.USER:
                        lc_history.append(HumanMessage(content=m.content))
                    else:
                        lc_history.append(AIMessage(content=m.content))

                # Run agent and yield steps as they happen
                response_text, trace = await self.agent_engine.run(
                    goal=user_message,
                    history=lc_history,
                    images=request.images
                )

                for step in trace:
                    yield {"data": json.dumps({'event': 'thought', 'data': step})}

                await self.memory.add_message(
                    session_id,
                    Message(role=Role.ASSISTANT, content=response_text),
                    request_id=request_id,
                    user_id=request.user_id
                )
                yield {"data": json.dumps({'event': 'token', 'data': response_text})}
                yield {"data": json.dumps({'event': 'done'})}
                return

            # ── STANDARD CHAT PATH ──
            await self.memory.add_message(
                session_id,
                Message(role=Role.USER, content=user_message),
                request_id=request_id,
                user_id=request.user_id,
            )

            intent_result = self.intent_classifier.classify(user_message)

            is_complex = len(user_message) > 60 or "?" in user_message
            dynamic_threshold = 0.75 if is_complex else 0.60

            # Same concurrent fetch as the non-streaming path: retrieval,
            # history, and routing all proceed in parallel.
            conversation_summary = await self.memory.get_conversation_summary(session_id)
            retrieval_results, conversation_history, model = await asyncio.gather(
                self.retrieval_engine.retrieve(
                    query=user_message,
                    session_id=session_id,
                    user_id=request.user_id,
                    db=db,
                    top_k=5,
                    conversation_summary=conversation_summary,
                    include_summary=False,
                ),
                self.memory.get_conversation(session_id),
                self.model_router.route(
                    intent=intent_result.intent,
                    preferred_model=request.model,
                ),
            )
            retrieval_results = [
                r for r in retrieval_results if self._passes_dynamic_threshold(r, dynamic_threshold)
            ]

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

            # Collect the raw tokens with a thin wrapper instead of parsing
            # every SSE frame back from JSON (which doubled JSON work per token).
            collected_tokens: list[str] = []

            async def _tee_tokens(stream: AsyncIterator[str]) -> AsyncIterator[str]:
                async for token in stream:
                    collected_tokens.append(token)
                    yield token

            async for sse_event in self.streaming_engine.stream_response(
                _tee_tokens(token_stream), model, check_disconnected=disconnect_event
            ):
                yield sse_event

            full_response = "".join(collected_tokens)
            if full_response:
                await self.memory.add_message(
                    session_id,
                    Message(role=Role.ASSISTANT, content=full_response),
                    request_id=request_id,
                    user_id=request.user_id,
                )
        except Exception as e:
            from kimiko.services.llm import ModelNotAvailableError
            if isinstance(e, ModelNotAvailableError):
                yield {
                    "data": json.dumps(
                        {
                            "event": "error",
                            "data": (
                                "⚠️ Model not found. Please run "
                                f"`ollama pull {str(e).split()[-1]}`"
                            ),
                        }
                    )
                }
                return
            raise
