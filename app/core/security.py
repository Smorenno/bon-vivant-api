import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from app.config import settings


def decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except ExpiredSignatureError:
        raise ValueError("token_expired")
    except InvalidTokenError:
        raise ValueError("token_invalid")
