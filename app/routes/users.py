from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps import get_db
from app.crud.user import create_user, get_user, get_all_users, delete_user
from app.schemas.user import UserCreate, UserOut
from typing import List

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/", response_model=UserOut)
async def create(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    return await create_user(db, payload.username, payload.email, payload.password, payload.role)

@router.get("/", response_model=List[UserOut])
async def list_users(db: AsyncSession = Depends(get_db)):
    return await get_all_users(db)

@router.get("/{user_id}", response_model=UserOut)
async def get_one(user_id: int, db: AsyncSession = Depends(get_db)):
    return await get_user(db, user_id)

@router.delete("/{user_id}")
async def delete(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await delete_user(db, user_id)
    if not user:
        return {"error": "user not found"}
    return {"deleted": user_id}