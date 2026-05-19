from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.database import engine, Base


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


@app.get("/health")
async def health():
    return {"status": "ok"}
