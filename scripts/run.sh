#!/bin/bash
# Run script for Chainlit + LangGraph Agent
# Supports both path-stripping and full-path-forwarding proxies
#
# Proxy path pattern: /{username}/proxy/{portNumber}
# Automatically detects username from $USER environment variable

set -e

# Activate virtual environment
source .venv/bin/activate

# Load environment variables from .env first (so user overrides are respected)
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

# Get current username for proxy path
USER_NAME=${USER:-$(whoami)}
PORT=${CHAINLIT_PORT:-8000}
HOST=${CHAINLIT_HOST:-0.0.0.0}

# Default proxy path uses current username
DEFAULT_PROXY_PATH="/${USER_NAME}/proxy/${PORT}"

echo "=========================================="
echo "Chainlit + LangGraph Agent Runner"
echo "=========================================="
echo ""

# Parse arguments
MODE=${1:-"auto"}

if [ "$MODE" == "help" ] || [ "$MODE" == "--help" ] || [ "$MODE" == "-h" ]; then
    echo "Usage: ./run.sh [MODE]"
    echo ""
    echo "Modes:"
    echo "  auto          - Auto-detect proxy mode (default)"
    echo "  local         - Run locally without proxy (no --root-path)"
    echo "  proxy-strip   - Run behind proxy that STRIPS path (most common)"
    echo "  proxy-full    - Run behind proxy that forwards FULL path"
    echo "  help          - Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./run.sh local              # Local development"
    echo "  ./run.sh proxy-strip        # Behind nginx, auto-tunnel, etc."
    echo "  ./run.sh proxy-full         # Behind proxy that keeps full path"
    echo ""
    echo "Proxy Behavior Explanation:"
    echo "  • proxy-strip: Proxy forwards https://domain.com/{username}/proxy/{port}/ → http://localhost:{port}/"
    echo "                 (path is stripped, but we use --root-path + middleware to rewrite it back)"
    echo "  • proxy-full:  Proxy forwards https://domain.com/{username}/proxy/{port}/ → http://localhost:{port}/{username}/proxy/{port}/"
    echo "                 (path is kept, USE --root-path directly)"
    echo ""
    echo "Current user: ${USER_NAME}"
    echo "Default proxy path: ${DEFAULT_PROXY_PATH}"
    echo ""
    exit 0
fi

# Check if .env is configured
if [ -z "$OPENAI_API_BASE_URL" ]; then
    echo "⚠️  WARNING: OPENAI_API_BASE_URL is not set in .env"
    echo "   Please configure your .env file before running."
    echo ""
fi

case "$MODE" in
    local)
        echo "Mode: Local Development (no proxy)"
        echo "URL: http://${HOST}:${PORT}/"
        echo ""
        chainlit run src/app.py -w --host "$HOST" --port "$PORT"
        ;;

    proxy-strip|auto)
        # Use run_server.py which sets CHAINLIT_ROOT_PATH before importing chainlit
        # and includes ProxyPathMiddleware for path rewriting
        if [ "$MODE" == "auto" ]; then
            echo "Mode: Auto-detect (defaulting to proxy-strip with middleware)"
        else
            echo "Mode: Proxy with Path Stripping + Middleware"
        fi
        echo "URL: http://${HOST}:${PORT}/"
        echo ""
        echo "✅ Using run_server.py with CHAINLIT_ROOT_PATH"
        echo "   Proxy strips path → Middleware rewrites → App sees full path"
        echo ""
        # Use CHAINLIT_PROXY_PATH from .env if set, otherwise use default
        if [ -z "$CHAINLIT_PROXY_PATH" ]; then
            export CHAINLIT_PROXY_PATH="${DEFAULT_PROXY_PATH}"
            echo "   Proxy Path: ${CHAINLIT_PROXY_PATH}/"
            echo "   (Auto-detected from username: ${USER_NAME})"
        else
            echo "   Proxy Path: ${CHAINLIT_PROXY_PATH}/"
            echo "   (From .env file)"
        fi
        echo ""
        python server/run_server.py
        ;;

    proxy-full)
        # Chainlit requires root_path without trailing slash
        ROOT_PATH="/${USER_NAME}/proxy/${PORT}"
        echo "Mode: Proxy with Full Path Forwarding"
        echo "URL: http://${HOST}:${PORT}${ROOT_PATH}/"
        echo "User: ${USER_NAME}"
        echo ""
        echo "✅ Running WITH --root-path ${ROOT_PATH}"
        echo "   Your proxy should forward the FULL path including the prefix"
        echo ""
        chainlit run src/app.py --root-path "$ROOT_PATH" -h --host "$HOST" --port "$PORT"
        ;;

    *)
        echo "❌ Unknown mode: $MODE"
        echo "   Run './run.sh help' for usage information"
        exit 1
        ;;
esac
