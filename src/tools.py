"""
Tools module for the LangGraph Agent.
Provides various tools that the agent can invoke.
"""

import json
import random
from typing import Any

from langchain_core.tools import tool


@tool
def search_web(query: str) -> str:
    """
    Search the web for information on a given topic.
    This is a simulated tool that returns mock results.
    """
    # Simulated web search results
    results = {
        "python programming": "Python is a high-level, interpreted programming language known for its readability.",
        "machine learning": "Machine learning is a subset of AI that enables systems to learn from data.",
        "langgraph": "LangGraph is a library for building stateful, multi-actor applications with LLMs.",
        "chainlit": "Chainlit is an open-source Python framework for building conversational AI interfaces.",
    }
    
    # Return matching result or a generic response
    for key, value in results.items():
        if key.lower() in query.lower():
            return f"Search results for '{query}': {value}"
    
    return f"Search results for '{query}': Found general information about this topic. (This is a simulated search tool)"


@tool
def calculate(expression: str) -> str:
    """
    Evaluate a mathematical expression.
    Use this for calculations, arithmetic operations, and math problems.
    """
    try:
        # Safe evaluation of mathematical expressions
        allowed_names = {
            "abs": abs,
            "max": max,
            "min": min,
            "pow": pow,
            "round": round,
            "sum": sum,
        }
        
        # Parse and evaluate the expression safely
        result = eval(expression, {"__builtins__": {}}, allowed_names)  # noqa: S307
        return f"The result of '{expression}' is: {result}"
    except Exception as e:
        return f"Error calculating '{expression}': {str(e)}"


@tool
def get_current_time() -> str:
    """
    Get the current date and time.
    """
    from datetime import datetime
    now = datetime.now()
    return f"Current date and time: {now.strftime('%Y-%m-%d %H:%M:%S')}"


@tool
def random_number(min_val: int = 1, max_val: int = 100) -> str:
    """
    Generate a random number within a specified range.
    """
    number = random.randint(min_val, max_val)  # noqa: S311
    return f"Random number between {min_val} and {max_val}: {number}"


@tool
def weather_info(location: str) -> str:
    """
    Get weather information for a location.
    This is a simulated weather tool.
    """
    weathers = ["sunny", "cloudy", "rainy", "windy", "snowy"]
    temp = random.randint(15, 35)  # noqa: S311
    condition = random.choice(weathers)  # noqa: S311
    return f"Weather in {location}: {condition.capitalize()}, {temp}°C (simulated data)"


# Export all tools
TOOLS = [
    search_web,
    calculate,
    get_current_time,
    random_number,
    weather_info,
]
