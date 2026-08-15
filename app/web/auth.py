import secrets

from fastapi import Request

from app.api.config import get_settings

SESSION_KEY = "authenticated"


class NotAuthenticated(Exception):
    """Raised by require_session; caught by an app-level handler that
    redirects to /ui/login (see app/api/main.py)."""


def check_password(password: str) -> bool:
    settings = get_settings()
    # Two independent shared passwords, either grants access — see
    # Settings.ui_password_1/2 for why there are two.
    return secrets.compare_digest(password, settings.ui_password_1) or secrets.compare_digest(
        password, settings.ui_password_2
    )


def require_session(request: Request) -> None:
    if not request.session.get(SESSION_KEY):
        raise NotAuthenticated()
