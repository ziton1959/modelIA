from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.core.deps import get_db
from app.crud.job import create_job, get_job, get_all_jobs
from app.crud.vm import get_vm
from app.schemas.job import JobCreate, JobOut
from app.models.job import Job
from app.routes.auth import get_current_user
from typing import List

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/", response_model=JobOut)
async def create(payload: JobCreate, db: AsyncSession = Depends(get_db)):
    return await create_job(db, payload.type, owner_id=1, vm_id=payload.vm_id)


@router.get("/", response_model=List[JobOut])
async def list_jobs(db: AsyncSession = Depends(get_db)):
    return await get_all_jobs(db)


@router.get("/mine/history")
async def my_history(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(Job).where(Job.owner_id == current_user.id).order_by(desc(Job.created_at))
    )
    jobs = result.scalars().all()
    out = []
    for j in jobs:
        vm = await get_vm(db, j.vm_id) if j.vm_id else None
        spec = vm.config if vm else {}
        out.append({
            "job_id": j.id,
            "vm_id": j.vm_id,
            "status": j.status,
            "template_name": (spec or {}).get("template_name", "vm-image"),
            "os": (spec or {}).get("os"),
            "created_at": j.created_at.isoformat() if j.created_at else None,
        })
    return out


@router.get("/mine/history/{job_id}")
async def my_history_detail(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    job = await get_job(db, job_id)
    if not job or job.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="not found")
    vm = await get_vm(db, job.vm_id) if job.vm_id else None
    return {
        "job_id": job.id,
        "status": job.status,
        "spec": vm.config if vm else {},
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


@router.get("/{job_id}", response_model=JobOut)
async def get_one(job_id: int, db: AsyncSession = Depends(get_db)):
    return await get_job(db, job_id)