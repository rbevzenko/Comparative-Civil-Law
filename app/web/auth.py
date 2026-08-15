import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.api.config import get_settings

basic_scheme = HTTPBasic()


def require_basic_auth(credentials: HTTPBasicCredentials = Depends(basic_scheme)) -> None:
    settings = get_settings()
    valid_user = secrets.compare_digest(credentials.username, settings.ui_basic_auth_username)
    valid_pass = secrets.compare_digest(credentials.password, settings.api_token)
    if not (valid_user and valid_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
