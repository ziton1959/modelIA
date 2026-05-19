from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps import get_db
from app.crud.job import create_job, get_job, get_all_jobs
from app.schemas.job import JobCreate, JobOut
from typing import List

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.post("/", response_model=JobOut)
async def create(payload: JobCreate, db: AsyncSession = Depends(get_db)):
    return await create_job(db, payload.type, owner_id=1, vm_id=payload.vm_id)

@router.get("/", response_model=List[JobOut])
async def list_jobs(db: AsyncSession = Depends(get_db)):
    return await get_all_jobs(db)

@router.get("/{job_id}", response_model=JobOut)
async def get_one(job_id: int, db: AsyncSession = Depends(get_db)):
    return await get_job(db, job_id)