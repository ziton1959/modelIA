from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import asyncio
from app.core.deps import get_db
from app.crud.vm import create_vm, get_vm
from app.crud.job import create_job, update_job, get_job
from app.database import AsyncSessionLocal
from app.routes.auth import get_current_user
from ai_agent.orchestrator import parse_vm_request, check_missing, finalize_spec
from ai_agent.executor import execute_pipeline
from app.core.settings_store import get_setting_sync

router = APIRouter(prefix="/api/vm", tags=["vm-create"])


class VMRequest(BaseModel):
    prompt: str
    partial_spec: dict | None = None   # accumulated answers on resubmit


async def run_pipeline_background(job_id: int, spec: dict):
    async with AsyncSessionLocal() as db:
        try:
            await update_job(db, job_id, status="running", logs="Pipeline started...")
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, execute_pipeline, spec, job_id)
            if result.get("status") == "completed":
                logs = result.get("packer_logs", "") + result.get("ansible_logs", "")
                await update_job(db, job_id, status="completed", logs=logs)
            else:
                error = result.get("error", "Unknown error")
                logs = result.get("packer_logs", "") + result.get("ansible_logs", "")
                await update_job(db, job_id, status="failed", logs=f"ERROR: {error}\n{logs}")
        except Exception as e:
            print(f"Background task error: {e}")
            async with AsyncSessionLocal() as db2:
                await update_job(db2, job_id, status="failed", logs=f"Exception: {str(e)}")


@router.post("/create")
async def create_vm_from_prompt(
    payload: VMRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # If the frontend sent an accumulated spec (answers to questions), use it.
    if payload.partial_spec:
        spec = payload.partial_spec
    else:
        spec = await parse_vm_request(payload.prompt)
        if "error" in spec:
            return {"status": "failed", "error": spec["error"]}

    # Check for anything missing / ambiguous / suggestible.
    questions = check_missing(spec)
    if questions:
        return {
            "status": "needs_input",
            "partial_spec": spec,
            "questions": questions,
        }

    # Complete — finalize and create the job (but don't build yet).
    spec = finalize_spec(spec)
    vm = await create_vm(
        db,
        name=spec["template_name"],
        template=spec["template_name"],
        config=spec,
        owner_id=current_user.id,
    )
    job = await create_job(
        db,
        type="vm.provision",
        owner_id=current_user.id,
        vm_id=vm.id,
    )
    return {"status": "pending", "job_id": job.id, "vm_id": vm.id, "spec": spec}


@router.post("/build/{job_id}")
async def start_build(
    job_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Maintenance mode: block new builds when the admin has enabled it.
    if get_setting_sync("maintenance_mode", "false").lower() == "true":
        raise HTTPException(
            status_code=503,
            detail="The platform is under maintenance. Builds are temporarily disabled.",
        )

    job = await get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status not in ("pending", "queued", "failed"):
        return {"status": job.status, "job_id": job_id,
                "message": "build already started or finished"}
    vm = await get_vm(db, job.vm_id)
    if vm is None:
        raise HTTPException(status_code=404, detail="vm not found")
    spec = vm.config
    background_tasks.add_task(run_pipeline_background, job_id, spec)
    return {"status": "queued", "job_id": job_id}