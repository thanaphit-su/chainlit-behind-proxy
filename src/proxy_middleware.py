"""
ASGI Middleware for handling path-stripping proxies.

This middleware solves the issue where a proxy strips the path prefix before
forwarding to the application, but the application needs to know the original
path for URL generation.

Proxy path pattern: /{username}/proxy/{portNumber}

Example proxy behavior:
    https://domain.com/{username}/proxy/{port}/  →  http://localhost:{port}/
    (proxy strips /{username}/proxy/{port}/ before forwarding)

The middleware rewrites incoming paths to include the root path, allowing
Chainlit's --root-path to work correctly for URL generation while the proxy
strips paths for routing.
"""

import getpass
import os
from typing import Any


class ProxyPathMiddleware:
    """
    Middleware that prepends a root path to incoming requests.
    
    This handles proxies that strip the path prefix before forwarding
    to the backend application.
    
    How it works:
    1. Proxy forwards https://domain.com/{username}/proxy/{port}/ → http://localhost:{port}/
    2. Middleware receives request to /
    3. Middleware rewrites path to /{username}/proxy/{port}/
    4. Chainlit routes handle the request normally
    
    For assets:
    1. Proxy forwards https://domain.com/{username}/proxy/{port}/assets/... → http://localhost:{port}/assets/...
    2. Middleware receives request to /assets/...
    3. Middleware rewrites path to /{username}/proxy/{port}/assets/...
    4. Chainlit serves the asset
    """
    
    def __init__(self, app: Any, root_path: str):
        self.app = app
        self.root_path = root_path.rstrip("/")
    
    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            
            # Rewrite paths that don't already have the root_path prefix
            # This handles path-stripping proxies
            if path == "/":
                new_path = self.root_path + "/"
                scope["path"] = new_path
                if "raw_path" in scope:
                    scope["raw_path"] = new_path.encode()
            elif not path.startswith(self.root_path + "/"):
                new_path = self.root_path + path
                scope["path"] = new_path
                if "raw_path" in scope:
                    scope["raw_path"] = new_path.encode()
            
            # Set root_path for URL generation in responses
            scope["root_path"] = self.root_path
        
        await self.app(scope, receive, send)


def patch_chainlit_app(root_path: str | None = None) -> None:
    """
    Patch Chainlit's ASGI app with the ProxyPathMiddleware.
    
    This should be called BEFORE Chainlit creates its app instance,
    typically at module import time in app.py.
    
    Args:
        root_path: The root path prefix (e.g., /{username}/proxy/{port})
                  If None, reads from CHAINLIT_PROXY_PATH env var or uses default
    """
    if root_path is None:
        user_name = getpass.getuser()
        port = os.getenv("CHAINLIT_PORT", "8000")
        default_path = f"/{user_name}/proxy/{port}"
        root_path = os.getenv("CHAINLIT_PROXY_PATH", default_path)
    
    if not root_path or root_path == "/":
        return  # No patching needed for root path
    
    try:
        import chainlit.server
        
        # We need to patch the app reference that chainlit.server uses
        # This must happen before the app is fully initialized
        original_app = chainlit.server.app
        
        # Create a wrapper that will apply our middleware when the app is accessed
        class AppProxy:
            def __init__(self, target_app, middleware):
                self._target_app = target_app
                self._middleware = middleware
                self._wrapped = None
            
            def _get_wrapped(self):
                if self._wrapped is None:
                    # Apply middleware to the actual app
                    self._wrapped = self._middleware(self._target_app)
                return self._wrapped
            
            async def __call__(self, scope, receive, send):
                app = self._get_wrapped()
                await app(scope, receive, send)
        
        chainlit.server.app = AppProxy(original_app, lambda app: ProxyPathMiddleware(app, root_path))
        print(f"✅ Patched Chainlit app with ProxyPathMiddleware (root_path={root_path})")
    except ImportError:
        pass  # Chainlit not installed or different version
