from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps import get_db
from app.crud.vm import create_vm
from app.crud.job import create_job
from app.schemas.vm import VMOut
from pydantic import BaseModel
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))
from ai_agent.orchestrator import parse_vm_request

router = APIRouter(prefix="/api/vm", tags=["vm-create"])


class VMRequest(BaseModel):
    prompt: str
    owner_id: int = 1


@router.post("/create")
async def create_vm_from_prompt(payload: VMRequest, db: AsyncSession = Depends(get_db)):
    spec = await parse_vm_request(payload.prompt)

    if "error" in spec:
        return {"status": "failed", "error": spec["error"]}

    vm = await create_vm(
        db,
        name=spec["template_name"],
        template=spec["template_name"],
        config=spec,
        owner_id=payload.owner_id
    )

    job = await create_job(
        db,
        type="vm.provision",
        owner_id=payload.owner_id,
        vm_id=vm.id
    )

    return {
        "status": "queued",
        "job_id": job.id,
        "vm_id": vm.id,
        "spec": spec
    }