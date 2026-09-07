"""
Custom ASGI entry point for Chainlit with proxy path support.

This app:
1. Sets CHAINLIT_ROOT_PATH env var BEFORE importing chainlit
   (ensures HTML templates generate correct URLs with proxy path prefix)
2. Wraps Chainlit's app with ProxyPathMiddleware
   (rewrites incoming paths from proxy to include the root path)

Proxy path pattern: /{username}/proxy/{portNumber}

For path-stripping proxies:
    https://domain.com/{username}/proxy/{port}/ → http://localhost:{port}/

Usage:
    uvicorn asgi_app:app --host 0.0.0.0 --port 8000

Or use the run_proxy.sh script.
"""

import getpass
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load environment variables from project root (where .env lives)
project_root = Path(__file__).parent.parent
load_dotenv(dotenv_path=project_root / ".env")

# Get current username for default proxy path
USER_NAME = getpass.getuser()
PORT = os.getenv("CHAINLIT_PORT", "8000")
DEFAULT_PROXY_PATH = f"/{USER_NAME}/proxy/{PORT}"

# Get proxy path from environment
PROXY_PATH = os.getenv("CHAINLIT_PROXY_PATH", DEFAULT_PROXY_PATH)

# Set Chainlit's root path environment variable BEFORE importing chainlit
# This ensures HTML templates generate correct URLs with the proxy path prefix
if PROXY_PATH and PROXY_PATH != "/":
    os.environ["CHAINLIT_ROOT_PATH"] = PROXY_PATH
    print(f"✅ Set CHAINLIT_ROOT_PATH={PROXY_PATH}")


class ProxyPathMiddleware:
    """
    ASGI Middleware that rewrites paths for path-stripping proxies.
    
    When a proxy strips the path prefix before forwarding (e.g.,
    https://domain.com/{username}/proxy/{port}/ → http://localhost:{port}/),
    this middleware rewrites the incoming path to include the original prefix.
    """
    
    def __init__(self, app: Any, root_path: str):
        self.app = app
        self.root_path = root_path.rstrip("/")
    
    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            
            # Rewrite paths that don't already have the root_path prefix
            if path == "/":
                scope["path"] = self.root_path + "/"
                if "raw_path" in scope:
                    scope["raw_path"] = (self.root_path + "/").encode()
            elif not path.startswith(self.root_path + "/"):
                scope["path"] = self.root_path + path
                if "raw_path" in scope:
                    scope["raw_path"] = (self.root_path + path).encode()
            
            # Set root_path for URL generation in responses
            scope["root_path"] = self.root_path
        
        await self.app(scope, receive, send)


# Import chainlit modules (this triggers chainlit's initialization)
# The CHAINLIT_ROOT_PATH env var is now set, so chainlit will use it for HTML
import chainlit.server as server_module  # noqa: E402

# The chainlit app (now with correct root_path for HTML generation)
chainlit_app = server_module.app

# Wrap with our middleware if proxy path is configured
if PROXY_PATH and PROXY_PATH != "/":
    app = ProxyPathMiddleware(chainlit_app, PROXY_PATH)
    print(f"✅ Wrapped with ProxyPathMiddleware (root_path={PROXY_PATH})")
else:
    app = chainlit_app
    print("ℹ️  Running without proxy path middleware")

# Import app.py to register chainlit handlers
# app.py is in the src/ directory
import importlib  # noqa: E402
importlib.import_module("src.app")
