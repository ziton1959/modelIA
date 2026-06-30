from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import jwt, JWTError
import os

# bcrypt is the proper password hash — salted and deliberately slow.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# In production, set these via env vars. The secret signs the JWT — keep it secret.
SECRET_KEY = os.getenv("JWT_SECRET", "change-this-to-a-long-random-string")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24h


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None