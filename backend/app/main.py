import asyncio
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import agents, auth, features, health, knowledge, patients, websocket
from app.config import settings
from app.database import Base, engine
from app.services.redis_client import redis_client
from app.tasks.scheduler import create_followup_tasks

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await redis_client.connect()
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    scheduler.add_job(create_followup_tasks, "cron", hour=8, minute=0, id="daily_followup")
    scheduler.start()
    yield
    scheduler.shutdown()
    await redis_client.disconnect()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(patients.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(features.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api")
app.include_router(websocket.router, prefix="/api")


@app.get("/")
async def root():
    return {"name": settings.app_name, "status": "running", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}
