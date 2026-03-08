"""Agent state definitions for LangGraph reasoning loops."""

from __future__ import annotations

from typing import Annotated, List, Optional, TypedDict, Union

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """The state of the agent reasoning loop.
    
    Attributes:
        messages: The history of messages in the conversation.
        next_step: The identifier for the next node to execute.
        thought: The internal reasoning of the agent.
        action: The tool to be called, if any.
        observation: The result of the last tool execution.
        step_count: Number of reasoning steps taken so far.
        max_steps: Maximum allowed steps (safeguard).
    """
    messages: Annotated[List[BaseMessage], add_messages]
    next_step: str
    thought: Optional[str]
    action: Optional[str]
    observation: Optional[str]
    step_count: int
    max_steps: int
    images: Optional[List[str]]
    trace: List[str]
