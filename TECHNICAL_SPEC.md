# TECHNICAL_SPEC.md — Chainlit + LangGraph Agentic Chat Application

## Project Overview

A **Simple Agent Chat Application** that integrates **Chainlit** (UI framework) with **LangGraph** (agentic loop orchestration) and connects to an **OpenAI Compatible API**. The application runs behind a reverse proxy with path stripping.

**Proxy Path Pattern:** `/{username}/proxy/{portNumber}` — automatically detected from the current system user, with override support via `.env`.

**Tech Stack:**
- **Chainlit** v2.12.0 — Conversational AI UI framework
- **LangGraph** v1.2.11 — Stateful multi-actor agent orchestration
- **LangChain-OpenAI** v1.6.0 — OpenAI Compatible API client
- **Python** 3.12 — Runtime
- **uv** — Package manager and virtual environment

---

## Project Structure

```
.
├── .env                      # Environment variables (user-configurable, gitignored)
├── .env.example              # Environment variables template
├── .gitignore                # Git ignore rules
├── .venv/                    # Virtual environment (created by uv, gitignored)
├── src/
│   ├── app.py                # Chainlit Application (entry point)
│   ├── agent.py              # LangGraph Agentic Loop implementation
│   ├── tools.py              # Tool definitions for the agent
│   └── proxy_middleware.py   # ASGI middleware for proxy path rewriting
├── server/
│   ├── asgi_app.py           # Custom ASGI app with proxy middleware
│   └── run_server.py         # Standalone server runner
├── scripts/
│   └── run.sh                # Convenience runner script
├── pyproject.toml            # Project configuration & dependencies
├── README.md                 # User-facing documentation
└── TECHNICAL_SPEC.md          # This file — technical specification
```

---

## Problem 1: Proxy Path Mismatch ("Invalid path")

### Symptom
When opening `localhost:8000`, the auto-tunnel system forwards to:
```
https://domain.com/{username}/proxy/{port}/ → http://localhost:{port}/
```

The proxy **strips the path prefix** `/{username}/proxy/{port}/` before forwarding to the backend. However, when using `chainlit run app.py --root-path /{username}/proxy/{port}`, the app expects requests at `http://localhost:{port}/{username}/proxy/{port}/`, resulting in **"Invalid path. Please specify correct URL and path"**.

### Root Cause
There are **two different proxy behaviors**:

| Proxy Type | Forward Rule | `--root-path` needed? |
|-----------|-------------|----------------------|
| **Path-Stripping** (our case) | `/path/` → `/` | NO — proxy strips path |
| **Full-Path** | `/path/` → `/path/` | YES — path preserved |

Our auto-tunnel uses **Path-Stripping** but we were using `--root-path`, causing a mismatch.

### Solution: Custom ASGI App with Dual-Layer Fix

Created `asgi_app.py` that handles **both problems simultaneously**:

#### Layer 1: HTML URL Generation (`CHAINLIT_ROOT_PATH`)
Set the environment variable **BEFORE** importing chainlit so HTML templates generate correct asset URLs:

```python
import getpass
user_name = getpass.getuser()
port = os.getenv("CHAINLIT_PORT", "8000")
proxy_path = f"/{user_name}/proxy/{port}"

os.environ["CHAINLIT_ROOT_PATH"] = proxy_path
import chainlit.server as server_module  # Now uses the env var
```

Chainlit's `get_html_template()` reads this env var and prefixes all asset URLs:
```html
<!-- Without: -->
<script src="/assets/index-B2u6IBgX.js"></script>

<!-- With CHAINLIT_ROOT_PATH: -->
<script src="/{username}/proxy/{port}/assets/index-B2u6IBgX.js"></script>
```

#### Layer 2: Request Path Rewriting (`ProxyPathMiddleware`)
ASGI middleware that rewrites incoming paths from the proxy back to include the root path:

```python
class ProxyPathMiddleware:
    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            if path == "/":
                scope["path"] = "/{username}/proxy/{port}/"
            elif not path.startswith("/{username}/proxy/{port}/"):
                scope["path"] = "/{username}/proxy/{port}" + path
        await self.app(scope, receive, send)
```

This ensures:
- `GET /` → `GET /{username}/proxy/{port}/` (matches Chainlit's routes)
- `GET /assets/...` → `GET /{username}/proxy/{port}/assets/...`

### Files Modified
- `server/asgi_app.py` — **new file**
- `server/run_server.py` — **new file**
- `scripts/run.sh` — updated `proxy-strip` mode to use `run_server.py`

---

## Problem 2: Agent Responds "I processed your request but didn't generate a response."

### Symptom
User sends "Hello" and the app responds: *"I processed your request but didn't generate a response."*

### Root Cause
**LangGraph `astream` yields states keyed by node name**, not a flat dictionary:

```python
# What astream yields:
{
    'reason': {'messages': [AIMessage(...)], 'iteration_count': 1},
    'act': {'messages': [], 'iteration_count': 1},
    'observe': {'messages': [...], 'iteration_count': 1}
}

# What the code was looking for:
state.get("messages", [])  # → [] (key doesn't exist at top level!)
```

The code `state.get("messages", [])` returned an empty list because `"messages"` is nested inside each node state.

### Solution: Extract Messages from Node States

Changed the message extraction logic to iterate over node states:

```python
async for state in agent.astream(message.content):
    # LangGraph astream yields states keyed by node name
    node_messages = []
    for node_name, node_state in state.items():
        if isinstance(node_state, dict) and "messages" in node_state:
            node_messages = node_state["messages"]
            break
    
    if not node_messages:
        continue
    
    last_message = node_messages[-1]
    # Process the message...
```

### Files Modified
- `src/app.py` — updated `on_message()` event loop

---

## Problem 3: Chat Not Streaming Token-by-Token

### Symptom
The response appears all at once instead of streaming character by character.

### Root Cause
The original code used `msg.update()` to update the entire message content, which updates the whole text at once:

```python
# OLD: Updates entire message at once
msg.content = full_response
await msg.update()  # Whole text re-rendered
```

### Solution: Use `msg.stream_token()`

Chainlit provides `stream_token()` for true token-by-token streaming:

```python
# NEW: Streams one token at a time
await msg.stream_token(token)
```

However, we also needed to switch from `astream()` to `astream_events()` to get individual tokens from the LLM:

```python
async for event in agent.graph.astream_events(initial_state, version="v2"):
    if event["event"] == "on_chat_model_stream":
        chunk = event["data"]["chunk"]
        if chunk.content:
            await msg.stream_token(chunk.content)
```

### Files Modified
- `src/app.py` — switched to `stream_token()`
- `src/agent.py` — added `astream_events()` method

---

## Problem 4: Tool Calls Appear After Summary Message + "Executing..." Stuck

### Symptom
1. Tool call step appears **below** the final response message
2. Tool step shows "Executing..." forever instead of the actual result
3. Tool result shows raw object representation instead of clean text

### Root Cause 4a: Wrong Element Type and Parent Relationship

The original code used `cl.Step` for tool calls with `parent_id=msg.id`:

```python
# OLD: Step as child of message
step = cl.Step(name=f"🔧 {tool_name}", type="tool")
step.input = tool_args
await step.send()  # Appears as child of msg
```

Chainlit renders `Step` elements with complex parent/child relationships that don't follow simple creation order. Steps can appear before, after, or nested within their parent message unpredictably.

### Root Cause 4b: Step Output Never Updated

The code created the step with `step.output = "Executing..."` but never updated it after the tool completed:

```python
# OLD: Output set once, never updated
step.output = "Executing..."
await step.send()
# ... tool runs ...
# Never calls step.update() with actual result!
```

### Root Cause 4c: Raw Object in Result

The tool result was passed directly without extracting the text content:

```python
# OLD: Raw object
step.output = result  # Could be a ToolMessage object, not a string
```

### Solution: Use `cl.Message` Instead of `cl.Step`

**Key Insight:** Chainlit displays `cl.Message` elements in strict creation order. By creating messages in the desired display order, we guarantee correct ordering.

#### New Flow (Creation Order = Display Order)

```python
# 1. Create thinking message FIRST (appears at top)
thinking_msg = cl.Message(content="**🤔 Thinking...**")
await thinking_msg.send()

# 2. Create tool messages when tools run (appear after thinking)
tool_msg = cl.Message(content=f"**🔧 {tool_name}**\n\n*Running...*")
await tool_msg.send()

# 3. Update tool message with result
tool_msg.content = f"**🔧 {tool_name}**\n```\n{clean_result}\n```"
await tool_msg.update()

# 4. Create final response message LAST (appears at bottom)
final_msg = cl.Message(content=final_text)
await final_msg.send()
```

#### Result Extraction Helper

```python
def _extract_result_text(result) -> str:
    """Extract clean text from tool result."""
    if isinstance(result, str):
        return result
    elif hasattr(result, "content"):
        return str(result.content)
    else:
        return str(result)
```

### Files Modified
- `src/app.py` — complete rewrite of `on_message()` using `cl.Message` instead of `cl.Step`

---

## Problem 5: Message Order Incorrect (Thinking After Response)

### Symptom
After fixing Problem 4, the order was:
1. Final response message (wrong — should be last)
2. Tool result message (wrong — should be before response)
3. Thinking step (wrong — should be first)

### Root Cause
The main response message `msg` was created **before** any tool or thinking elements:

```python
# OLD: msg created first
msg = cl.Message(content="")  # Created FIRST → appears FIRST
await msg.send()

# Thinking and tools created later → appear AFTER msg
```

### Solution: Delay Message Creation

Create the final response message **only when the final response actually starts streaming** (i.e., on the 2nd+ agent iteration):

```python
# NEW: msg created when final response starts
if agent_count >= 2 and msg is None:
    msg = cl.Message(content="")  # Created AFTER thinking + tools
    await msg.send()  # Appears at the BOTTOM

await msg.stream_token(chunk.content)
```

### Files Modified
- `src/app.py` — restructured message creation timing

---

## Problem 6: Graph Structure Not Supporting Streaming Events

### Symptom
`astream_events` wasn't yielding `on_chat_model_stream` events properly because the LLM was wrapped inside a Python function node.

### Root Cause
The original graph wrapped the LLM inside a `reason()` function:

```python
# OLD: LLM inside a function
def reason(state):
    response = self.llm_with_tools.invoke(messages)  # .invoke() is synchronous!
    return {"messages": [response]}

workflow.add_node("reason", reason)
```

When the node is a Python function that calls `.invoke()`, LangGraph can't intercept the individual tokens.

### Solution: Use LangGraph Prebuilt Components

Refactored to use `MessagesState` and `ToolNode` from `langgraph.prebuilt`:

```python
# NEW: Direct LLM as node function
def agent_node(state: MessagesState) -> dict:
    messages = state["messages"]
    response = self.llm_with_tools.invoke(messages)
    return {"messages": [response]}

# Use prebuilt ToolNode
tool_node = ToolNode(tools=TOOLS)

workflow.add_node("agent", agent_node)
workflow.add_node("tools", tool_node)
```

This structure allows `astream_events` to properly capture `on_chat_model_stream` events.

### Files Modified
- `src/agent.py` — complete rewrite using `MessagesState`, `ToolNode`, and simplified graph structure

---

## Problem 7: Proxy Path Not Respecting `.env` Configuration

### Symptom
User sets `CHAINLIT_PROXY_PATH=/thanaphits/proxy/8000` in `.env`, but `run.sh` outputs:
```
Proxy Path: /coder/proxy/8000/
User: coder
```

The script ignores the `.env` value and auto-detects from `$USER` instead.

### Root Cause
`run.sh` did **not load `.env`** before checking `CHAINLIT_PROXY_PATH`. It only used the bash `$USER` variable to construct the default path:

```bash
# OLD: No .env loading!
USER_NAME=${USER:-$(whoami)}
DEFAULT_PROXY_PATH="/${USER_NAME}/proxy/${PORT}"
# ... later ...
export CHAINLIT_PROXY_PATH="${DEFAULT_PROXY_PATH}"  # Always uses $USER
```

### Solution: Load `.env` Before Using Variables

Added `.env` loader at the top of `run.sh` (before any variable usage):

```bash
#!/bin/bash

# Load environment variables from .env first
if [ -f .env ]; then
    while IFS='=' read -r key value || [ -n "$key" ]; do
        case "$key" in
            ''|\#*) continue ;;
        esac
        key=$(echo "$key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        value=$(echo "$value" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        [ -z "$key" ] && continue
        export "$key=$value"
    done < .env
fi

# Now check if user has overridden CHAINLIT_PROXY_PATH
if [ -z "$CHAINLIT_PROXY_PATH" ]; then
    export CHAINLIT_PROXY_PATH="${DEFAULT_PROXY_PATH}"
    echo "   (Auto-detected from username: ${USER_NAME})"
else
    echo "   (From .env file)"
fi
```

### Priority Order

1. **`.env` file** — highest priority (user override)
2. **Auto-detect from `$USER`** — fallback if `.env` not set
3. **Default pattern** — `/{username}/proxy/{portNumber}`

### Files Modified
- `scripts/run.sh` — added `.env` loader and conditional proxy path selection

---

## Problem 8: `.env` Not Loading When Running from Subdirectories

### Symptom
When running `python server/run_server.py` from the project root, everything works. But when running from a subdirectory or the app fails to find `.env`, the LLM returns:

```json
{"detail": "Model '' was not found"}
```

The model name is an empty string `''`, indicating `OPENAI_MODEL` was not loaded from `.env`.

### Root Cause
`python-dotenv`'s `load_dotenv()` loads from the **current working directory** by default, not from the file's location:

```python
# OLD: Loads from CWD, not from project root
load_dotenv()  # Looks for .env in current directory
```

When running `server/run_server.py`, if the CWD is `server/`, it looks for `server/.env` which doesn't exist.

### Solution: Explicitly Specify `.env` Path

Use `pathlib` to compute the project root relative to the current file, then pass the absolute path to `load_dotenv()`:

```python
from pathlib import Path
from dotenv import load_dotenv

# Compute project root (parent of the directory containing this file)
project_root = Path(__file__).parent.parent

# Load .env from project root explicitly
load_dotenv(dotenv_path=project_root / ".env")
```

**Applied to all files that need environment variables:**

| File | `.env` Loading |
|------|---------------|
| `server/asgi_app.py` | `load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")` |
| `server/run_server.py` | `load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")` |
| `src/agent.py` | `load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")` |
| `src/app.py` | `load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")` |

### Key Insight

Always use **absolute paths** for `.env` loading in projects with subdirectories:

```python
# ✅ Good: Explicit path
project_root = Path(__file__).parent.parent
load_dotenv(dotenv_path=project_root / ".env")

# ❌ Bad: Implicit CWD-dependent
load_dotenv()  # Breaks when CWD changes
```

### Files Modified
- `server/asgi_app.py` — added explicit `.env` path
- `server/run_server.py` — added explicit `.env` path
- `src/agent.py` — added explicit `.env` path
- `src/app.py` — added explicit `.env` path

---

## Agentic Loop Architecture

### Components

```
Trigger: User sends message
    ↓
Reason (agent node): LLM processes messages and plans
    ↓ (if tool_calls present)
Act (tools node): ToolNode executes tools
    ↓
Observe (implicit): Results added to message history
    ↓ (loop back to Reason)
Reason (agent node): LLM processes tool results
    ↓ (if no tool_calls)
Stop: Return final response
```

### Graph Structure

```
START → agent → [tools → agent]* → END
         ↓
      should_continue()
      (tool_calls? → tools : → END)
```

### Event Flow in UI

```
User: "What time is it?"
    ↓
[🤔 Thinking...]          ← First agent iteration (reasoning)
    "I need to check the current time for the user..."
    ✅ Decided to use tools
    ↓
[🔧 get_current_time]      ← Tool execution
    ```
    Current date and time: 2026-09-07 06:15:14
    ```
    ↓
[The current time is...]  ← Final agent iteration (response)
    "The current time is 6:15 AM (06:15:14) on September 7, 2026."
```

---

## Configuration

### Environment Variables (`.env`)

```env
# OpenAI Compatible API Configuration
OPENAI_API_BASE_URL=https://ism.bgrimm.io/api/v1
OPENAI_API_KEY=sk-...
OPENAI_MODEL=Gemini 3.6 Flash

# Application Configuration
CHAINLIT_PORT=8000

# Proxy Configuration (auto-detected from username if not set)
# Pattern: /{username}/proxy/{portNumber}
# Example: CHAINLIT_PROXY_PATH=/thanaphits/proxy/8000
```

### Proxy Path Resolution

The proxy path is resolved in this order:

1. **`CHAINLIT_PROXY_PATH` in `.env`** — if set, use this value
2. **Auto-detect from system** — `/{current_user}/proxy/{port}`

Example for user `thanaphits` on port `8000`:
```bash
# If .env has: CHAINLIT_PROXY_PATH=/thanaphits/proxy/8000
# Result: /thanaphits/proxy/8000

# If .env is empty or not set
# Result: /coder/proxy/8000 (assuming current user is "coder")
```

### Proxy Modes (`run.sh`)

| Mode | Use Case | Command |
|------|----------|---------|
| `local` | Development, no proxy | `./run.sh local` |
| `proxy-strip` | Proxy strips path (most common) | `./run.sh proxy-strip` |
| `proxy-full` | Proxy forwards full path | `./run.sh proxy-full` |

---

## How `run.sh` Works

### `.env` Loading Pattern

The script **must load `.env` before using any environment variables** to ensure user overrides are respected:

```bash
#!/bin/bash
set -e

# Step 1: Activate virtual environment
source .venv/bin/activate

# Step 2: Load .env FIRST (before using any env vars)
if [ -f .env ]; then
    while IFS='=' read -r key value || [ -n "$key" ]; do
        case "$key" in
            ''|\#*) continue ;;  # Skip comments and empty lines
        esac
        # Trim whitespace from key and value
        key=$(echo "$key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        value=$(echo "$value" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        [ -z "$key" ] && continue
        export "$key=$value"
    done < .env
fi

# Step 3: Compute defaults AFTER loading .env
USER_NAME=${USER:-$(whoami)}
PORT=${CHAINLIT_PORT:-8000}
HOST=${CHAINLIT_HOST:-0.0.0.0}
DEFAULT_PROXY_PATH="/${USER_NAME}/proxy/${PORT}"
```

**Critical:** If you load `.env` *after* setting defaults, the user's `.env` values will be ignored.

### Proxy Path Resolution Logic

```bash
# Step 4: Resolve proxy path with priority
if [ -z "$CHAINLIT_PROXY_PATH" ]; then
    # .env not set or empty → use auto-detected default
    export CHAINLIT_PROXY_PATH="${DEFAULT_PROXY_PATH}"
    echo "   (Auto-detected from username: ${USER_NAME})"
else
    # .env has value → use it
    echo "   (From .env file)"
fi
```

**Priority Order:**
1. `CHAINLIT_PROXY_PATH` from `.env` (highest priority)
2. Auto-detect from `$USER` (fallback)
3. Pattern: `/{username}/proxy/{portNumber}`

### Mode Selection

```bash
MODE=${1:-"auto"}

case "$MODE" in
    local)
        # No proxy, direct access
        chainlit run src/app.py -w --host "$HOST" --port "$PORT"
        ;;
    
    proxy-strip|auto)
        # Use custom ASGI app with middleware
        export CHAINLIT_PROXY_PATH="${CHAINLIT_PROXY_PATH}"
        python server/run_server.py
        ;;
    
    proxy-full)
        # Use chainlit's built-in --root-path
        ROOT_PATH="/${USER_NAME}/proxy/${PORT}"
        chainlit run src/app.py --root-path "$ROOT_PATH" -h --host "$HOST" --port "$PORT"
        ;;
esac
```

---

## Tools Available

| Tool | Description | Example Output |
|------|-------------|----------------|
| `search_web` | Simulated web search | "Search results for 'python': Python is a high-level..." |
| `calculate` | Math expression evaluator | "The result of '2+2' is: 4" |
| `get_current_time` | Current datetime | "Current date and time: 2026-09-07 06:15:14" |
| `random_number` | Random number generator | "Random number between 1 and 100: 42" |
| `weather_info` | Simulated weather | "Weather in Bangkok: Sunny, 32°C (simulated data)" |

---

## Key Design Decisions

### 1. Why `cl.Message` over `cl.Step`?

`cl.Step` has complex parent/child rendering logic that makes ordering unpredictable. `cl.Message` renders in strict creation order, giving us full control over display order.

### 2. Why `astream_events` over `astream`?

`astream` yields complete node states. `astream_events` yields fine-grained events (`on_chat_model_stream`, `on_tool_start`, `on_tool_end`) that allow real-time UI updates.

### 3. Why Custom ASGI App?

The standard `chainlit run` command doesn't allow setting environment variables before chainlit imports. Our `asgi_app.py` sets `CHAINLIT_ROOT_PATH` before `import chainlit`, ensuring HTML templates generate correct URLs.

### 4. Why `run_server.py` instead of `chainlit run`?

`run_server.py` gives us full control over the uvicorn server and allows us to:
- Set env vars before imports
- Configure logging
- Handle proxy path consistently

### 5. Why Dynamic Proxy Path Detection?

The proxy path pattern `/{username}/proxy/{portNumber}` is shared infrastructure. By auto-detecting the username from the system:
- **New users** can run the app immediately without editing code
- **Existing users** can override via `.env` if needed
- **No hardcoded usernames** in the codebase

---

## Testing Checklist

- [x] App loads without errors
- [x] Proxy path works (`/{username}/proxy/{port}/`)
- [x] `.env` proxy path override works
- [x] Assets load correctly (JS, CSS)
- [x] WebSocket connects
- [x] Simple greeting works (no tools)
- [x] Tool calls work (e.g., "What time is it?")
- [x] Token streaming works
- [x] Thinking display works
- [x] Tool result display works
- [x] Message ordering is correct
- [x] Tool status updates from "Running..." to result
- [x] `.env` loads correctly from project root regardless of CWD

---

## Known Limitations

1. **Simulated Tools**: `search_web` and `weather_info` return mock data. Replace with real API calls for production.
2. **No Persistence**: Chat history is not persisted. Add a database for production.
3. **No Authentication**: The app is open to all users. Add auth for production.
4. **Single Session**: No multi-user session isolation.

---

## Future Enhancements

1. Add real web search (SerpAPI, Bing API, etc.)
2. Add persistent chat history (SQLite, PostgreSQL)
3. Add user authentication (OAuth, JWT)
4. Add file upload support
5. Add multi-modal support (images, audio)
6. Add conversation branching (LangGraph's checkpointing)

---

## References

- [Chainlit Documentation](https://docs.chainlit.io/)
- [Chainlit + LangGraph Integration](https://docs.chainlit.io/integrations/langchain)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [LangGraph Prebuilt Components](https://langchain-ai.github.io/langgraph/reference/prebuilt/)
- [OpenAI Compatible API](https://platform.openai.com/docs/api-reference)

---

*Document Version: 1.1*
*Last Updated: 2026-09-07*
