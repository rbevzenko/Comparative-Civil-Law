import hashlib
import hmac
import secrets
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.config import get_settings

bearer_scheme = HTTPBearer(auto_error=False)


async def require_api_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    settings = get_settings()
    if credentials is None or not secrets.compare_digest(credentials.credentials, settings.api_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# --- signed public citation links (GET /source/{chunk_id}) ----------------
#
# universal_ref needs to be clickable by anyone reading a citation — no
# login, no API token — while still not being a bare, guessable/enumerable
# "give me any chunk by id" endpoint that would let someone scrape the whole
# corpus one UUID at a time. The signature proves the link was minted by
# this server (attached to a specific chunk_id it already knows), without
# requiring a session or a new secret to deploy: it's derived from the
# existing session-cookie signing key via domain separation, so it rotates
# together with that key and needs no extra configuration.


def _source_link_key(settings) -> bytes:
    return hashlib.sha256(f"source-link:{settings.session_secret_key}".encode()).digest()


def sign_chunk_id(chunk_id: uuid.UUID) -> str:
    settings = get_settings()
    mac = hmac.new(_source_link_key(settings), str(chunk_id).encode(), hashlib.sha256)
    return mac.hexdigest()[:24]


def verify_chunk_signature(chunk_id: uuid.UUID, sig: str | None) -> bool:
    if not sig:
        return False
    return hmac.compare_digest(sign_chunk_id(chunk_id), sig)


def build_universal_ref(chunk_id: uuid.UUID) -> str | None:
    """Public, citable URL for a chunk — the corpus's equivalent of the
    other connectors' universal_ref. None if MCP_DOMAIN isn't configured
    (local/dev runs with no public hostname to build a URL from)."""
    settings = get_settings()
    if not settings.mcp_domain:
        return None
    return f"https://{settings.mcp_domain}/source/{chunk_id}?sig={sign_chunk_id(chunk_id)}"
