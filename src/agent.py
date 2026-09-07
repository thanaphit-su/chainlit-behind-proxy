"""
LangGraph Agent module.
Implements an agentic loop with the following components:
- Trigger: User message initiates the process
- Reason: LLM processes and plans next steps
- Act: Invoke tools based on the plan
- Observe: Read and evaluate tool results
- Stop Rules: Stop when goal is achieved, error occurs, or max iterations reached

This version uses LangGraph prebuilt ToolNode and MessagesState for better
integration with Chainlit's LangchainCallbackHandler.
"""

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState
from langgraph.prebuilt import ToolNode

from src.tools import TOOLS

# Load environment variables from project root
project_root = Path(__file__).parent.parent
load_dotenv(dotenv_path=project_root / ".env")


class AgenticLoop:
    """
    Agentic Loop implementation with LangGraph.
    
    Uses LangGraph's prebuilt ToolNode and MessagesState for cleaner code
    and better streaming support.
    
    Components:
    1. Trigger: User message starts the loop
    2. Reason: LLM thinks and decides on actions
    3. Act: Execute tools
    4. Observe: Evaluate results
    5. Stop Rules: Max iterations or goal achieved
    """
    
    def __init__(self, max_iterations: int = 5):
        self.max_iterations = max_iterations
        
        # Initialize LLM with OpenAI Compatible API
        base_url = os.getenv("OPENAI_API_BASE_URL", "")
        api_key = os.getenv("OPENAI_API_KEY", "")
        model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
        
        if not base_url:
            raise ValueError("OPENAI_API_BASE_URL is not set in .env file")
        
        self.llm = ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=model,
            temperature=0.7,
            streaming=True,
        )
        
        # Bind tools to the LLM
        self.llm_with_tools = self.llm.bind_tools(TOOLS)
        
        # Build the graph
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine using prebuilt components."""
        
        # System message to guide the agent's behavior
        system_message = SystemMessage(content=(
            "You are a helpful AI assistant with access to tools. "
            "Think step by step and use tools when necessary. "
            "After using tools, analyze the results and provide a clear response."
        ))
        
        def agent_node(state: MessagesState) -> dict:
            """
            Agent node: LLM processes messages and decides next actions.
            This is the 'Think' phase of the agentic loop.
            """
            messages = state["messages"]
            
            # Add system message at the beginning if not present
            if not any(isinstance(m, SystemMessage) for m in messages):
                messages = [system_message] + messages
            
            # Call LLM with tools
            response = self.llm_with_tools.invoke(messages)
            
            return {"messages": [response]}
        
        def should_continue(state: MessagesState) -> Literal["tools", "__end__"]:
            """
            Stop Rules: Determine if the loop should continue or stop.
            """
            messages = state["messages"]
            last_message = messages[-1]
            
            # If the LLM makes a tool call, route to the "tools" node
            if last_message.tool_calls:
                return "tools"
            
            # Otherwise, stop (reply to the user)
            return "__end__"
        
        # Create prebuilt ToolNode
        tool_node = ToolNode(tools=TOOLS)
        
        # Build graph
        workflow = StateGraph(MessagesState)
        
        # Add nodes
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", tool_node)
        
        # Add edges
        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges(
            "agent",
            should_continue,
        )
        workflow.add_edge("tools", "agent")
        
        return workflow.compile()
    
    async def ainvoke(self, user_message: str):
        """
        Async invoke the agent with a user message.
        
        Args:
            user_message: The user's input message
            
        Returns:
            Final state messages
        """
        from langchain_core.messages import HumanMessage
        
        initial_state = {"messages": [HumanMessage(content=user_message)]}
        
        final_state = await self.graph.ainvoke(initial_state)
        return final_state["messages"]
    
    async def astream_events(self, user_message: str):
        """
        Async stream the agent's execution with detailed events.
        
        Uses LangGraph's astream_events to yield individual tokens,
        tool calls, and tool results for real-time UI updates.
        
        Args:
            user_message: The user's input message
            
        Yields:
            Dict with 'type' and 'data' keys:
            - type='token': data is the token string
            - type='tool_call': data is tool call info dict
            - type='tool_result': data is tool result string
            - type='thinking': data is thinking/reasoning text
            - type='error': data is the error message
        """
        from langchain_core.messages import HumanMessage
        
        initial_state = {"messages": [HumanMessage(content=user_message)]}
        
        try:
            async for event in self.graph.astream_events(
                initial_state,
                version="v2",
            ):
                event_type = event.get("event", "")
                
                # Handle LLM token streaming
                if event_type == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content"):
                        token = chunk.content
                        if token:
                            yield {"type": "token", "data": token}
                
                # Handle tool call start
                elif event_type == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    tool_input = event.get("data", {}).get("input", {})
                    yield {
                        "type": "tool_call",
                        "data": {
                            "name": tool_name,
                            "args": tool_input,
                        }
                    }
                
                # Handle tool result
                elif event_type == "on_tool_end":
                    result = event.get("data", {}).get("output", "")
                    yield {"type": "tool_result", "data": result}
        
        except Exception as e:
            yield {"type": "error", "data": str(e)}
