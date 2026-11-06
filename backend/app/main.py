import asyncio
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import agents, auth, features, health, knowledge, medication, patients, reminders, voice, websocket
from app.config import settings
from app.database import Base, engine
from app.services.redis_client import redis_client
from app.tasks.scheduler import (
    consolidate_inactive_sessions,
    dispatch_due_appointments,
    dispatch_due_reminders,
)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await redis_client.connect()
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        # 轻量迁移：create_all 不会给既有表加列，这里幂等补齐
        await conn.execute(
            text(
                "ALTER TABLE health_records "
                "ADD COLUMN IF NOT EXISTS source_document_id INTEGER"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_health_records_source_document_id "
                "ON health_records (source_document_id)"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE medical_documents "
                "ALTER COLUMN status TYPE VARCHAR(50)"
            )
        )
    scheduler.add_job(dispatch_due_reminders, "interval", minutes=1, id="med_reminder")
    scheduler.add_job(dispatch_due_appointments, "interval", minutes=30, id="appointment_reminder")
    scheduler.add_job(consolidate_inactive_sessions, "interval", minutes=30, id="memory_consolidate")
    scheduler.start()
    yield
    # 关闭顺序要点：scheduler 用 wait=False，避免 reload/restart 时卡在
    # 「Waiting for background tasks to complete」，导致端口不释放、新进程起不来。
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass
    try:
        await redis_client.disconnect()
    except Exception:
        pass
    try:
        await engine.dispose()
    except Exception:
        pass


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
app.include_router(reminders.router, prefix="/api")
app.include_router(medication.router, prefix="/api")
app.include_router(voice.router, prefix="/api")
app.include_router(websocket.router, prefix="/api")


@app.get("/")
async def root():
    return {"name": settings.app_name, "status": "running", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}
