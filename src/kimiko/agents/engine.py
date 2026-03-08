"""Agent engine — orchestrates the LangGraph reasoning loop and tool execution."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Union

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage
from langgraph.graph import END, StateGraph

from kimiko.agents.prompts import REACT_SYSTEM_PROMPT, TOOL_TEMPLATE
from kimiko.agents.state import AgentState
from kimiko.services.llm import get_llm_service
from kimiko.tools.registry import ToolRegistry
from kimiko.tools.executor import ToolExecutor

logger = structlog.get_logger(__name__)


class AgentEngine:
    """Core reasoning engine using LangGraph to implement ReAct or Plan-Execute loops."""

    def __init__(
        self, 
        tool_registry: ToolRegistry,
        executor: Optional[ToolExecutor] = None,
        max_steps: int = 5
    ) -> None:
        self.registry = tool_registry
        self.executor = executor or ToolExecutor()
        self.max_steps = max_steps
        self._graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine."""
        workflow = StateGraph(AgentState)

        # Nodes
        workflow.add_node("reason", self.reason)
        workflow.add_node("act", self.act)

        # Edges
        workflow.set_entry_point("reason")
        
        # Conditional edges from reason
        workflow.add_conditional_edges(
            "reason",
            self._should_continue,
            {
                "continue": "act",
                "end": END
            }
        )
        
        # Act always goes back to reason
        workflow.add_edge("act", "reason")

        return workflow.compile()

    def _should_continue(self, state: AgentState) -> str:
        """Decide whether to execute an action or end the loop."""
        if state.get("next_step") == "end" or state["step_count"] >= state["max_steps"]:
            return "end"
        return "continue"

    async def reason(self, state: AgentState) -> Dict[str, Any]:
        """Reasoning node: Calls LLM to determine the next step."""
        llm = get_llm_service()
        
        # Format tool descriptions for the prompt
        tools = self.registry.list_tools()
        tools_description = "\n".join([
            TOOL_TEMPLATE.format(
                name=t.name, 
                description=t.description, 
                schema=t.args_schema.model_json_schema() if t.args_schema else "{}"
            )
            for t in tools
        ])
        
        system_msg = SystemMessage(
            content=REACT_SYSTEM_PROMPT.format(tools_description=tools_description)
        )
        
        # Prepare messages for LLM (User and Assistant turns)
        messages = state["messages"]
        
        # Convert to string prompt
        prompt = ""
        for m in messages:
            role = "Assistant" if isinstance(m, AIMessage) else "User"
            prompt += f"{role}: {m.content}\n"
        
        prompt += "Assistant: Thought:" 
        
        logger.info("agent_reasoning_start", step=state["step_count"] + 1)
        
        # Use new structured generate API
        model_name = state.get("model", "qwen2.5")
        if state.get("images"):
            model_name = "qwen2-vl"

        response = await llm.generate(
            model=model_name,
            prompt=prompt,
            system=REACT_SYSTEM_PROMPT.format(tools_description=tools_description),
            images=state.get("images"),
            temperature=0.1, # Agents need even lower temperature for tool reliability
        )
        
        text = response.get("response", "")
        full_text = "Thought:" + text # Restore prefix deleted for prompt engineering
        
        # Parse Thought / Action / Final Answer
        thought_match = re.search(r"Thought:(.*?)(?=Action:|Final Answer:|$)", full_text, re.S)
        action_match = re.search(r"Action:\s*(.*)", full_text)
        action_input_match = re.search(r"Action Input:\s*({.*})", full_text, re.S)
        final_answer_match = re.search(r"Final Answer:\s*(.*)", full_text, re.S)
        
        thought = thought_match.group(1).strip() if thought_match else ""
        
        updates = {
            "thought": thought,
            "messages": [AIMessage(content=full_text)],
            "step_count": state["step_count"] + 1,
            "trace": (state.get("trace") or []) + [f"Thought: {thought}"]
        }
        
        if final_answer_match:
            updates["next_step"] = "end"
            logger.info(
                "agent_step_trace",
                step=state["step_count"] + 1,
                thought=thought,
                conclusion=final_answer_match.group(1).strip()
            )
        elif action_match:
            updates["action"] = action_match.group(1).strip()
            # Parse input as JSON
            try:
                input_str = action_input_match.group(1).strip() if action_input_match else "{}"
                updates["action_input"] = json.loads(input_str)
            except json.JSONDecodeError:
                updates["action_input"] = {}
            updates["next_step"] = "act"
            
            logger.info(
                "agent_step_trace",
                step=state["step_count"] + 1,
                thought=thought,
                action=updates["action"],
                action_input=updates["action_input"]
            )
        else:
            # Fallback — maybe it just stopped without Final Answer
            updates["next_step"] = "end"
            
        return updates

    async def act(self, state: AgentState) -> Dict[str, Any]:
        """Acting node: Executes the selected tool."""
        tool_name = state.get("action")
        tool_input = state.get("action_input", {})
        
        if not tool_name:
            return {"observation": "Error: No action specified."}
            
        tool = self.registry.get_tool(tool_name)
        if not tool:
            return {"observation": f"Error: Tool '{tool_name}' not found."}
            
        observation = await self.executor.execute(tool, **tool_input)
        
        # Add observation back to history
        obs_msg = HumanMessage(content=f"Observation: {observation}")
        
        return {
            "observation": observation,
            "messages": [obs_msg],
            "trace": (state.get("trace") or []) + [f"Observation: {observation}"]
        }

    async def run(self, goal: str, history: List[BaseMessage] | None = None, images: list[str] | None = None) -> tuple[str, list[str]]:
        """Run the agent until it reaches a conclusion or max steps."""
        initial_state: AgentState = {
            "messages": (history or []) + [HumanMessage(content=goal)],
            "next_step": "reason",
            "thought": None,
            "action": None,
            "observation": None,
            "step_count": 0,
            "max_steps": self.max_steps,
            "images": images or [],
            "trace": []
        }
        
        final_state = await self._graph.ainvoke(initial_state)
        trace = final_state.get("trace", [])
        
        # Extract final answer from messages
        last_msg = final_state["messages"][-1].content
        answer = last_msg
        if "Final Answer:" in last_msg:
            answer = last_msg.split("Final Answer:")[-1].strip()
            
        return answer, trace
