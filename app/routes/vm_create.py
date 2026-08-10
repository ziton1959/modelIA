from ai_agent.orchestrator import parse_vm_request, check_missing, finalize_spec

class VMRequest(BaseModel):
    prompt: str
    partial_spec: dict | None = None   # accumulated answers on resubmit

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

    # Complete — finalize and create the job.
    spec = finalize_spec(spec)
    vm = await create_vm(db, name=spec["template_name"], template=spec["template_name"],
                         config=spec, owner_id=current_user.id)
    job = await create_job(db, type="vm.provision", owner_id=current_user.id, vm_id=vm.id)
    return {"status": "pending", "job_id": job.id, "vm_id": vm.id, "spec": spec}