from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from server.database.connection import SessionLocal
from server.models import ApiKey
from server.utils.helpers import sha256_of_token

# Routes that don't require any auth
PUBLIC_PATHS = {"/login", "/health"}
STATIC_PREFIX = "/static"

# Routes that require Bearer token (API)
BEARER_PATHS = {"/sync/check", "/sync/upload", "/upload"}

# Routes that require admin role
ADMIN_PREFIX = "/admin"


def _get_session_user(request: Request) -> dict | None:
    return request.session.get("user")


def _get_bearer_key(request: Request, db: Session) -> ApiKey | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    token_hash = sha256_of_token(token)
    key = db.query(ApiKey).filter(ApiKey.key_hash == token_hash, ApiKey.revoked.is_(False)).first()
    return key


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Always allow public paths and static files
        if path in PUBLIC_PATHS or path.startswith(STATIC_PREFIX):
            return await call_next(request)

        # Bearer-only API paths
        if path in BEARER_PATHS or (request.method == "POST" and path == "/upload"):
            accepts_json = "application/json" in request.headers.get("accept", "")
            db = SessionLocal()
            try:
                key = _get_bearer_key(request, db)
                if key is None:
                    if accepts_json:
                        return JSONResponse({"detail": "Invalid or missing API key"}, status_code=401)
                    return RedirectResponse(url="/login", status_code=302)
                request.state.api_key = key
            finally:
                db.close()
            return await call_next(request)

        # Allow Bearer auth on any path (read-only API access)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            db = SessionLocal()
            try:
                key = _get_bearer_key(request, db)
                if key:
                    request.state.api_key = key
                    return await call_next(request)
            finally:
                db.close()

        # Session-based paths
        user = _get_session_user(request)

        if user is None:
            return RedirectResponse(url="/login", status_code=302)

        # Admin-only paths
        if path.startswith(ADMIN_PREFIX) and "admin" not in user.get("roles", []):
            return RedirectResponse(url="/login", status_code=302)

        request.state.user = user
        return await call_next(request)
