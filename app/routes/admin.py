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