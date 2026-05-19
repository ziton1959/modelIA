from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.job import Job

async def create_job(db: AsyncSession, type: str, owner_id: int, vm_id: int = None):
    job = Job(type=type, owner_id=owner_id, vm_id=vm_id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job

async def get_job(db: AsyncSession, job_id: int):
    result = await db.execute(select(Job).where(Job.id == job_id))
    return result.scalar_one_or_none()

async def get_all_jobs(db: AsyncSession):
    result = await db.execute(select(Job))
    return result.scalars().all()