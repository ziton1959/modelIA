from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps import get_db
from app.crud.user import (
    create_user, get_user_by_username, get_user_by_email, get_user,
)
from app.core.security import verify_password, create_access_token, decode_token
from app.schemas.user import UserCreate, UserLogin, UserOut, Token
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter(prefix="/auth", tags=["auth"])
security_scheme = HTTPBearer()


@router.post("/signup", response_model=Token)
async def signup(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    if await get_user_by_username(db, payload.username):
        raise HTTPException(status_code=400, detail="username already taken")
    if await get_user_by_email(db, payload.email):
        raise HTTPException(status_code=400, detail="email already registered")
    user = await create_user(db, payload.username, payload.email, payload.password, payload.role)
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer", "user": user}


@router.post("/login", response_model=Token)
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_username(db, payload.username)
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="invalid username or password")
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer", "user": user}


# Dependency: read the JWT, return the current user. Protect routes with this.
async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
):
    payload = decode_token(creds.credentials)
    if payload is None or "sub" not in payload:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    user = await get_user(db, int(payload["sub"]))
    if user is None:
        raise HTTPException(status_code=401, detail="user not found")
    return user


@router.get("/me", response_model=UserOut)
async def me(current_user=Depends(get_current_user)):
    return current_user