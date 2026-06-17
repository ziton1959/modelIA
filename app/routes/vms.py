from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps import get_db
from app.crud.vm import create_vm, get_vm, get_all_vms, delete_vm
from app.schemas.vm import VMCreate, VMOut
from typing import List

router = APIRouter(prefix="/vms", tags=["vms"])

@router.post("/", response_model=VMOut)
async def create(payload: VMCreate, db: AsyncSession = Depends(get_db)):
    return await create_vm(db, payload.name, payload.template, payload.config, owner_id=1)

@router.get("/", response_model=List[VMOut])
async def list_vms(db: AsyncSession = Depends(get_db)):
    return await get_all_vms(db)

@router.get("/{vm_id}", response_model=VMOut)
async def get_one(vm_id: int, db: AsyncSession = Depends(get_db)):
    return await get_vm(db, vm_id)

@router.delete("/{vm_id}")
async def delete(vm_id: int, db: AsyncSession = Depends(get_db)):
    vm = await delete_vm(db, vm_id)
    if not vm:
        return {"error": "vm not found"}
    return {"deleted": vm_id}