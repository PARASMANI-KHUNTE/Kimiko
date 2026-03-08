"""Agent endpoint — POST /v1/agent/run."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from kimiko.api.deps import get_orchestrator
from kimiko.api.middleware.auth import verify_api_key
from kimiko.core.orchestrator import RequestOrchestrator
from kimiko.models.schemas import AgentTaskRequest, AgentTaskResponse

router = APIRouter(prefix="/agent", tags=["agent"])

logger = structlog.get_logger(__name__)


@router.post("/run", response_model=AgentTaskResponse)
async def run_agent_task(
    body: AgentTaskRequest,
    orchestrator: RequestOrchestrator = Depends(get_orchestrator),
    _auth: dict = Depends(verify_api_key),
) -> AgentTaskResponse:
    """Execute an autonomous task using the AI Agent.
    
    The agent will reason, use tools, and provide a final answer.
    """
    request_id = structlog.contextvars.get_contextvars().get("request_id")
    session_id = body.session_id or request_id or "default"
    
    logger.info("agent_task_received", goal=body.goal, session_id=session_id)
    
    try:
        # Update engine settings from request
        if body.max_steps:
            orchestrator.agent_engine.max_steps = body.max_steps
            
        if body.images:
            await orchestrator.scheduler.schedule_vision(orchestrator.vision_engine.get_vision_model())
        else:
            await orchestrator.scheduler.schedule_chat("qwen2.5")
            
        answer, trace = await orchestrator.agent_engine.run(
            goal=body.goal,
            images=body.images
            # history=history # TODO: Load history from memory
        )
        
        return AgentTaskResponse(
            id=request_id or "unknown",
            goal=body.goal,
            answer=answer,
            steps=trace,
            session_id=session_id
        )
    except Exception as e:
        logger.error("agent_task_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent execution failed: {str(e)}"
        )
