import hmac, time
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config.settings import settings

bearer = HTTPBearer(auto_error=False)


def check_credentials(u: str, p: str) -> bool:
    if not (settings.DEMO_USERNAME and settings.DEMO_PASSWORD):
        return False
    ok_u = hmac.compare_digest(u.encode(), settings.DEMO_USERNAME.encode())
    ok_p = hmac.compare_digest(p.encode(), settings.DEMO_PASSWORD.encode())
    return ok_u and ok_p


def issue_token(user: str) -> str:
    return jwt.encode({"sub": user, "exp": int(time.time()) + 8 * 3600}, settings.JWT_SECRET, algorithm="HS256")


def require_user(cred: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    if not cred:
        raise HTTPException(401, "Please sign in to continue.")
    try:
        return jwt.decode(cred.credentials, settings.JWT_SECRET, algorithms=["HS256"])["sub"]
    except Exception:
        raise HTTPException(401, "Your session has expired. Please sign in again.")
