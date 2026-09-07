#!/usr/bin/env python3
"""
Standalone server runner for Chainlit with proxy support.
This script starts uvicorn with the correct configuration.

Proxy path pattern: /{username}/proxy/{portNumber}
Automatically detects username from environment.
"""

import getpass
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env BEFORE any os.getenv() calls
project_root = Path(__file__).parent.parent
load_dotenv(dotenv_path=project_root / ".env")

# Get current username for default proxy path
USER_NAME = getpass.getuser()
PORT = os.getenv("CHAINLIT_PORT", "8000")
DEFAULT_PROXY_PATH = f"/{USER_NAME}/proxy/{PORT}"

# Set proxy path before anything else
PROXY_PATH = os.getenv("CHAINLIT_PROXY_PATH", DEFAULT_PROXY_PATH)
if PROXY_PATH and PROXY_PATH != "/":
    os.environ["CHAINLIT_ROOT_PATH"] = PROXY_PATH
    print(f"✅ Set CHAINLIT_ROOT_PATH={PROXY_PATH}")

# Now import and run
import uvicorn

if __name__ == "__main__":
    host = os.getenv("CHAINLIT_HOST", "0.0.0.0")
    port = int(PORT)
    
    print(f"🚀 Starting Chainlit app on http://{host}:{port}/")
    print(f"   Proxy path: {PROXY_PATH}")
    print(f"   User: {USER_NAME}")
    print(f"   Pattern: /{{username}}/proxy/{{port}}")
    print()
    
    # Change to project root so uvicorn can find 'server.asgi_app:app'
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    sys.path.insert(0, project_root)
    
    uvicorn.run(
        "server.asgi_app:app",
        host=host,
        port=port,
        log_level="info",
    )
