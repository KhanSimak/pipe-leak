"""
PHASE 5 — COMPLETE
All phases combined:
  ✅ Graph modeling + CRUD
  ✅ Hazen-Williams physics
  ✅ Leak injection + TimescaleDB history
  ✅ WebSocket streaming + Celery monitor
  ✅ Leak detection algorithm + diagnosis
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.models.db import Base, engine
from app.models.readings import PressureReading
from app.routers import networks, simulation, streaming, diagnosis
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(title="Pipe Leak Simulator — Phase 5 (Complete)", lifespan=lifespan)
app.include_router(networks.router,   prefix="/networks", tags=["networks"])
app.include_router(simulation.router, prefix="/networks", tags=["simulation"])
app.include_router(streaming.router,  prefix="/networks", tags=["streaming"])
app.include_router(diagnosis.router,  prefix="/networks", tags=["diagnosis"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)   