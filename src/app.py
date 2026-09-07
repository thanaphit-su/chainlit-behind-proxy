"""
Chainlit Application with LangGraph Agent.

Fixed message ordering:
1. Thinking message (first)
2. Tool result messages (if any)
3. Final response message (last)

Each element is a separate cl.Message created in the desired display order.
This ensures correct ordering regardless of parent/child relationships.

To run behind a proxy with a custom root path:
    ./run.sh proxy-strip
"""

import os
from pathlib import Path

import chainlit as cl
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from src.agent import AgenticLoop

# Load environment variables from project root
project_root = Path(__file__).parent.parent
load_dotenv(dotenv_path=project_root / ".env")


@cl.on_chat_start
async def on_chat_start():
    """Initialize the agent when a chat session starts."""
    try:
        agent = AgenticLoop(max_iterations=5)
        cl.user_session.set("agent", agent)
        await cl.Message(
            content="Hello! I'm an AI agent with tool-calling capabilities. "
                    "I can search the web, calculate expressions, check the time, "
                    "generate random numbers, and check weather information. "
                    "How can I help you today?"
        ).send()
    except ValueError as e:
        await cl.Message(
            content=f"⚠️ **Configuration Error**: {str(e)}\n\n"
                    f"Please make sure you have configured your `.env` file with:\n"
                    f"- `OPENAI_API_BASE_URL`: Your OpenAI compatible API endpoint\n"
                    f"- `OPENAI_API_KEY`: Your API key\n"
                    f"- `OPENAI_MODEL`: The model name to use"
        ).send()


@cl.on_message
async def on_message(message: cl.Message):
    """
    Handle incoming messages with CORRECT ordering.
    
    Chainlit displays messages in creation order.
    So we create them in the order we want them to appear:
    1. Thinking message (created immediately)
    2. Tool messages (created when tools run)
    3. Final response (created when final response starts)
    """
    agent = cl.user_session.get("agent")
    
    if not agent:
        await cl.Message(
            content="Agent is not initialized. Please check your configuration."
        ).send()
        return
    
    # State tracking
    thinking_text = ""
    final_text = ""
    agent_count = 0
    current_node = None
    
    # === STEP 1: Create thinking message FIRST ===
    # This ensures it appears at the TOP
    thinking_msg = cl.Message(content="**🤔 Thinking...**")
    await thinking_msg.send()
    
    # Track tool messages
    tool_msgs = {}  # tool_name -> cl.Message
    
    try:
        async for event in agent.graph.astream_events(
            {"messages": [HumanMessage(content=message.content)]},
            version="v2",
        ):
            metadata = event.get("metadata", {})
            node_name = metadata.get("langgraph_node", "")
            event_type = event.get("event", "")
            
            # Track which agent iteration we're on
            if node_name and node_name != current_node:
                current_node = node_name
                if node_name == "agent":
                    agent_count += 1
            
            # === TOKEN STREAMING ===
            if event_type == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and chunk.content:
                    if agent_count == 1:
                        # FIRST agent execution = THINKING phase
                        thinking_text += chunk.content
                        thinking_msg.content = f"**🤔 Thinking...**\n\n{thinking_text}"
                        await thinking_msg.update()
                    elif agent_count >= 2:
                        # SECOND+ agent execution = FINAL RESPONSE
                        # Buffer the text, we'll stream it later
                        final_text += chunk.content
            
            # === DETECT TOOL CALLS (end of first agent node) ===
            elif event_type == "on_chain_end" and node_name == "agent" and agent_count == 1:
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict) and "messages" in output:
                    messages = output["messages"]
                    if messages:
                        last_msg = messages[-1]
                        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                            # Agent decided to use tools
                            thinking_msg.content = (
                                f"**🤔 Thinking...**\n\n{thinking_text}\n\n"
                                f"✅ *Decided to use tools*"
                            )
                            await thinking_msg.update()
            
            # === TOOL CALL START ===
            elif event_type == "on_tool_start":
                tool_name = event.get("name", "unknown")
                tool_input = event.get("data", {}).get("input", {})
                
                # Create tool message (appears after thinking)
                tool_msg = cl.Message(
                    content=f"**🔧 {tool_name}**\n\n*Running...*"
                )
                await tool_msg.send()
                tool_msgs[tool_name] = tool_msg
            
            # === TOOL CALL END ===
            elif event_type == "on_tool_end":
                tool_name = event.get("name", "unknown")
                result = event.get("data", {}).get("output", "")
                
                clean_result = _extract_result_text(result)
                
                if tool_name in tool_msgs:
                    tool_msg = tool_msgs[tool_name]
                    tool_msg.content = f"**🔧 {tool_name}**\n```\n{clean_result}\n```"
                    await tool_msg.update()
        
        # === STEP 3: Create final response message LAST ===
        # This ensures it appears at the BOTTOM
        if final_text:
            final_msg = cl.Message(content=final_text)
            await final_msg.send()
        elif thinking_text:
            # No tools used, thinking IS the response
            # Update thinking message to show completion
            thinking_msg.content = f"**💭 Thought**\n\n{thinking_text}"
            await thinking_msg.update()
        else:
            await cl.Message(
                content="I processed your request but didn't generate a response."
            ).send()
    
    except Exception as e:
        await cl.Message(content=f"❌ **Error**: {str(e)}").send()
        import traceback
        traceback.print_exc()


def _extract_result_text(result) -> str:
    """Extract clean text from tool result."""
    if isinstance(result, str):
        return result
    elif hasattr(result, "content"):
        return str(result.content)
    else:
        return str(result)


@cl.on_chat_end
async def on_chat_end():
    """Clean up when a chat session ends."""
    cl.user_session.set("agent", None)


if __name__ == "__main__":
    pass
