"""认证模块（基于会话 Cookie 的简单登录）"""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Request, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.config import settings

serializer = URLSafeTimedSerializer(settings.secret_key, salt="ephemeris-auth")
SESSION_COOKIE = "ephemeris_session"


def create_session_token(username: str) -> str:
    return serializer.dumps({"username": username})


def verify_session_token(token: str) -> Optional[str]:
    try:
        data = serializer.loads(token, max_age=7 * 24 * 3600)  # 7 天有效期
        return data.get("username")
    except (BadSignature, SignatureExpired):
        return None


def get_current_user(request: Request) -> str:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    username = verify_session_token(token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="会话已过期")
    return username


def require_admin(request: Request) -> str:
    return get_current_user(request)
