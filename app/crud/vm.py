from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.vm import VM

async def create_vm(db: AsyncSession, name: str, template: str, config: dict, owner_id: int):
    vm = VM(name=name, template=template, config=config, owner_id=owner_id)
    db.add(vm)
    await db.commit()
    await db.refresh(vm)
    return vm

async def get_vm(db: AsyncSession, vm_id: int):
    result = await db.execute(select(VM).where(VM.id == vm_id))
    return result.scalar_one_or_none()

async def get_all_vms(db: AsyncSession):
    result = await db.execute(select(VM))
    return result.scalars().all()

async def delete_vm(db: AsyncSession, vm_id: int):
    vm = await get_vm(db, vm_id)
    if vm:
        await db.delete(vm)
        await db.commit()
    return vm