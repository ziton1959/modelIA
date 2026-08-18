from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from app.core.deps import get_db
from app.routes.auth import require_admin
from app.models.job import Job
from app.models.vm import VM
from app.models.user import User
from app.crud.user import get_user, delete_user
from ai_agent.executor import _minio_client, BUILT_BUCKET
import socket
import httpx
from datetime import datetime, timedelta
from collections import Counter

router = APIRouter(prefix="/admin", tags=["admin"])


# ---- 1. All builds across all users ----
@router.get("/builds")
async def all_builds(
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    result = await db.execute(select(Job).order_by(desc(Job.created_at)))
    jobs = result.scalars().all()
    out = []
    for j in jobs:
        # get owner username
        owner = await get_user(db, j.owner_id) if j.owner_id else None
        # get spec from VM
        vm = None
        if j.vm_id:
            r = await db.execute(select(VM).where(VM.id == j.vm_id))
            vm = r.scalar_one_or_none()
        spec = (vm.config if vm else {}) or {}
        out.append({
            "job_id": j.id,
            "owner": owner.username if owner else "unknown",
            "owner_id": j.owner_id,
            "status": j.status,
            "template_name": spec.get("template_name", "—"),
            "os": spec.get("os"),
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        })
    return out


# ---- 2. User management ----
@router.get("/users")
async def list_users(
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()
    # count builds per user
    out = []
    for u in users:
        cnt = await db.execute(select(func.count(Job.id)).where(Job.owner_id == u.id))
        build_count = cnt.scalar() or 0
        out.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "role": u.role,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "build_count": build_count,
        })
    return out


@router.patch("/users/{user_id}/role")
async def change_role(
    user_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    new_role = payload.get("role")
    if new_role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="role must be 'user' or 'admin'")
    user = await get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    user.role = new_role
    await db.commit()
    return {"id": user_id, "role": new_role}


@router.delete("/users/{user_id}")
async def remove_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="cannot delete yourself")
    user = await delete_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return {"deleted": user_id}


@router.get("/storage")
async def storage_overview(admin=Depends(require_admin)):
    client = _minio_client()
    objects = list(client.list_objects(BUILT_BUCKET))
    total_bytes = 0
    images = []
    for obj in objects:
        size = obj.size or 0
        total_bytes += size
        images.append({
            "name": obj.object_name,
            "size_mb": round(size / 1024 / 1024),
            "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
        })
    images.sort(key=lambda x: x["size_mb"], reverse=True)
    return {
        "image_count": len(images),
        "total_gb": round(total_bytes / 1024 / 1024 / 1024, 2),
        "images": images,
    }

@router.delete("/images/{image_name}")
async def delete_image(image_name: str, admin=Depends(require_admin)):
    object_name = image_name if image_name.endswith(".qcow2") else f"{image_name}.qcow2"
    client = _minio_client()
    try:
        client.remove_object(BUILT_BUCKET, object_name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"could not delete: {e}")
    return {"deleted": object_name}
def _check_tcp(host, port, timeout=2):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

@router.get("/health")
async def system_health(admin=Depends(require_admin)):
    services = {}
    # PostgreSQL
    services["postgres"] = _check_tcp("localhost", 5432)
    # Redis
    services["redis"] = _check_tcp("localhost", 6379)
    # MinIO
    services["minio"] = _check_tcp("127.0.0.1", 9000)
    # Ollama
    ollama_up = False
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get("http://127.0.0.1:11434/api/tags")
            ollama_up = r.status_code == 200
    except Exception:
        ollama_up = False
    services["ollama"] = ollama_up
    return {"services": services, "all_healthy": all(services.values())}

@router.get("/stats/overview")
async def stats_overview(db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    # all jobs
    result = await db.execute(select(Job))
    jobs = result.scalars().all()

    total_builds = len(jobs)
    completed = sum(1 for j in jobs if j.status == "completed")
    failed = sum(1 for j in jobs if j.status == "failed")
    finished = completed + failed
    success_rate = round((completed / finished) * 100) if finished else 0

    # users count
    ucount = await db.execute(select(func.count(User.id)))
    total_users = ucount.scalar() or 0

    # storage
    try:
        from ai_agent.executor import _minio_client, BUILT_BUCKET
        client = _minio_client()
        total_bytes = sum((o.size or 0) for o in client.list_objects(BUILT_BUCKET))
        storage_gb = round(total_bytes / 1024 / 1024 / 1024, 2)
    except Exception:
        storage_gb = 0

    # builds per day (last 14 days)
    today = datetime.utcnow().date()
    days = [(today - timedelta(days=i)) for i in range(13, -1, -1)]
    per_day = {d.isoformat(): 0 for d in days}
    for j in jobs:
        if j.created_at:
            key = j.created_at.date().isoformat()
            if key in per_day:
                per_day[key] += 1
    builds_per_day = [{"date": d[5:], "count": c} for d, c in per_day.items()]  # d[5:] = MM-DD

    # status breakdown
    status_counter = Counter(j.status for j in jobs)
    status_breakdown = [{"status": s, "count": c} for s, c in status_counter.items()]

    # builds by OS (from VM config)
    os_counter = Counter()
    for j in jobs:
        if j.vm_id:
            r = await db.execute(select(VM).where(VM.id == j.vm_id))
            vm = r.scalar_one_or_none()
            if vm and vm.config:
                os_name = (vm.config.get("os") or "unknown")
                # normalize (e.g. "Ubuntu 22.04" -> "Ubuntu")
                short = os_name.split()[0] if os_name != "unknown" else "unknown"
                os_counter[short] += 1
    builds_by_os = [{"os": o, "count": c} for o, c in os_counter.items()]

    return {
        "total_builds": total_builds,
        "success_rate": success_rate,
        "total_users": total_users,
        "storage_gb": storage_gb,
        "builds_per_day": builds_per_day,
        "status_breakdown": status_breakdown,
        "builds_by_os": builds_by_os,
    }