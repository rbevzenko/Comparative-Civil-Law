import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.config import get_settings

MCP_PATH_PREFIX = "/mcp"


class MCPTokenMiddleware(BaseHTTPMiddleware):
    """Gates /mcp behind a static token.

    Claude.ai's custom connector dialog has no field for a bearer token or
    custom header, only a URL — so the token travels as a query param baked
    into the connector URL (.../mcp?token=...). A header is also accepted
    for other MCP clients (e.g. local testing with curl).
    """

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith(MCP_PATH_PREFIX):
            return await call_next(request)

        settings = get_settings()
        token = request.query_params.get("token")
        if token is None:
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[len("Bearer ") :]

        if token is None or not secrets.compare_digest(token, settings.mcp_access_token):
            # 404, not 401: don't advertise that an MCP endpoint lives here.
            return JSONResponse({"detail": "Not Found"}, status_code=404)

        return await call_next(request)
