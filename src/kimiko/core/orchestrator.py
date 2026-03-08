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
    Message,
    Role,
    TokenUsage,
)
from kimiko.services.llm import LLMServiceError, get_llm_service
from kimiko.services.model_scheduler import ModelScheduler
from kimiko.tools.core import CalculatorTool, FileSystemTool
from kimiko.tools.registry import ToolRegistry
from kimiko.tools.search import WebSearchTool

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
        
        # Load external plugins dynammically from src/kimiko/plugins/installed/
        self.plugin_manager = PluginManager(self.tool_registry)
        loaded_plugins = self.plugin_manager.load_plugins()
        logger.info("plugins_loaded", count=loaded_plugins)
        
        self.agent_engine = AgentEngine(self.tool_registry)
        self.vision_engine = VisionEngine()
        
        self.scheduler = ModelScheduler()

    async def process(
        self,
        request: ChatRequest,
        db: AsyncSession | None = None,
        request_id: str | None = None,
    ) -> ChatResponse:
        """Process a non-streaming chat request through the full pipeline.

        Pipeline:
        1. Parse request + extract user message
        2. Store user message in session
        3. Classify intent
        4. Retrieve relevant context (memories, knowledge)
        5. Build prompt with token budgeting
        6. Route to appropriate model
        7. Execute LLM generation
        8. Store assistant response
        9. Return response
        """
        request_id = request_id or str(uuid.uuid4())[:8]
        start_time = time.time()

        # Extract user message (last message in the list)
        user_message = request.message
        session_id = request.session_id or request_id

        logger.info(
            "pipeline_start",
            request_id=request_id,
            session_id=session_id,
            message_preview=user_message[:80],
        )

        # 1. Store user message in session
        await self.memory.add_message(
            session_id,
            Message(role=Role.USER, content=user_message),
            request_id=request_id,
            user_id=request.user_id
        )

        # 2. Classify intent
        intent_result = self.intent_classifier.classify(user_message)

        # 3. Route model
        model = await self.model_router.route(
            intent=intent_result.intent,
            preferred_model=request.model,
        )

        # 4. Retrieval step
        retrieval_results = await self.retrieval_engine.retrieve(
            query=user_message,
            session_id=session_id,
            user_id=request.user_id,
            db=db,
            top_k=10,
        )

        # 5. Get conversation history + summary
        conversation_history = await self.memory.get_conversation(session_id)
        conversation_summary = await self.memory.get_conversation_summary(session_id)

        # 6. Build prompt
        prompt = self.context_builder.build(
            user_message=user_message,
            model=model,
            conversation_history=conversation_history[:-1],  # Exclude current message
            retrieval_results=retrieval_results,
            conversation_summary=conversation_summary,
        )

        # 7. Execute LLM
        try:
            # Phase 3.5: Schedule Models to prevent VRAM overflow
            if request.images:
                await self.scheduler.schedule_vision(model)
            else:
                await self.scheduler.schedule_chat(model)

            with LLM_GENERATION_DURATION.labels(model=model).time():
                llm = get_llm_service()
                
                # Handle multimodal prompt dict or string
                # The LLMService is expected to handle the dict format directly
                result = await llm.generate(
                    model=model,
                    prompt=prompt,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                )
        except LLMServiceError as e:
            LLM_ERRORS.labels(model=model, error_type=type(e).__name__).inc()
            logger.error("llm_generation_failed", error=str(e), model=model)
            raise

        response_text = result.get("response", "")

        # 8. Store assistant response
        await self.memory.add_message(
            session_id,
            Message(role=Role.ASSISTANT, content=response_text),
            request_id=request_id,
            user_id=request.user_id
        )

        # 9. Build response
        duration = time.time() - start_time
        logger.info(
            "pipeline_complete",
            request_id=request_id,
            model=model,
            intent=intent_result.intent.value,
            duration=f"{duration:.2f}s",
        )

        return ChatResponse(
            id=request_id,
            message=Message(role=Role.ASSISTANT, content=response_text),
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
        """Process a streaming chat request.

        Same pipeline as process(), but streams LLM tokens via SSE.
        """
        request_id = request_id or str(uuid.uuid4())[:8]
        user_message = request.message
        session_id = request.session_id or request_id

        # Store user message
        await self.memory.add_message(
            session_id,
            Message(role=Role.USER, content=user_message),
            request_id=request_id,
        )

        # Intent + route
        intent_result = self.intent_classifier.classify(user_message)
        model = await self.model_router.route(
            intent=intent_result.intent,
            preferred_model=request.model,
        )

        # Retrieve context
        retrieval_results = await self.retrieval_engine.retrieve(
            query=user_message,
            session_id=session_id,
            user_id=request.user_id,
            db=db,
        )

        conversation_history = await self.memory.get_conversation(session_id)
        conversation_summary = await self.memory.get_conversation_summary(session_id)

        # Build prompt
        prompt = self.context_builder.build(
            user_message=user_message,
            model=model,
            conversation_history=conversation_history[:-1],
            retrieval_results=retrieval_results,
            conversation_summary=conversation_summary,
        )

        # Stream from LLM
        if request.images:
            await self.scheduler.schedule_vision(model)
        else:
            await self.scheduler.schedule_chat(model)
            
        llm = get_llm_service()
        token_stream = llm.stream(
            model=model,
            prompt=prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        # Wrap in SSE with backpressure
        collected_tokens: list[str] = []

        async for sse_event in self.streaming_engine.stream_response(
            token_stream, model, check_disconnected=disconnect_event
        ):
            # Collect tokens for storage
            import json
            try:
                data = json.loads(sse_event.replace("data: ", "").strip())
                if data.get("event") == "token":
                    collected_tokens.append(data.get("data", ""))
            except (json.JSONDecodeError, ValueError):
                pass

            yield sse_event

        # Store complete assistant response
        full_response = "".join(collected_tokens)
        if full_response:
            await self.memory.add_message(
                session_id,
                Message(role=Role.ASSISTANT, content=full_response),
                request_id=request_id,
            )

        logger.info(
            "stream_pipeline_complete",
            request_id=request_id,
            model=model,
            tokens=len(collected_tokens),
        )
