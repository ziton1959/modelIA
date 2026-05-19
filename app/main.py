from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.database import engine, Base
from app.routes.users import router as users_router
from app.routes.vms import router as vms_router
from app.routes.jobs import router as jobs_router
from app.routes.vm_create import router as vm_create_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="Image Factory API",
    version="0.1.0",
    lifespan=lifespan
)

app.include_router(users_router)
app.include_router(vms_router)
app.include_router(jobs_router)
app.include_router(vm_create_router)


@app.get("/health")
async def health():
    return {"status": "ok"}