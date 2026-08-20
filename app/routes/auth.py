from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps import get_db
from app.crud.user import (
    create_user, get_user_by_username, get_user_by_email, get_user,
)
from app.core.security import verify_password, create_access_token, decode_token
from app.schemas.user import UserCreate, UserLogin, UserOut, Token
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.security import hash_password
from pydantic import BaseModel

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
    if not getattr(user, "is_active", True):
        raise HTTPException(status_code=403, detail="account is archived")
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
async def require_admin(current_user=Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="admin access required")
    return current_user


@router.get("/me", response_model=UserOut)
async def me(current_user=Depends(get_current_user)):
    return current_user


class ChangePassword(BaseModel):
    current_password: str
    new_password: str

class ChangeEmail(BaseModel):
    new_email: str
    current_password: str   # require password to change email (security)

@router.patch("/me/password")
async def change_my_password(
    payload: ChangePassword,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="current password is incorrect")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="new password must be at least 6 characters")
    current_user.hashed_password = hash_password(payload.new_password)
    await db.commit()
    return {"status": "password updated"}

@router.patch("/me/email")
async def change_my_email(
    payload: ChangeEmail,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="password is incorrect")
    # check the new email isn't taken
    existing = await get_user_by_email(db, payload.new_email)
    if existing and existing.id != current_user.id:
        raise HTTPException(status_code=400, detail="email already in use")
    current_user.email = payload.new_email
    await db.commit()
    return {"status": "email updated", "email": current_user.email}

