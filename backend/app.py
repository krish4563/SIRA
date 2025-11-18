from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings

# --- Existing Routers ---
from routers import health, memory, research
from routers.scheduler import router as scheduler_router

# --- NEW (Scheduler) ---
from services.scheduler import restore_jobs_from_disk, start_scheduler

app = FastAPI(title="SIRA Backend", version=settings.api_version)


# -------------------------
# CORS (unchanged)
# -------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------
# Existing Routers (unchanged)
# -------------------------
app.include_router(health.router, prefix="/health")
app.include_router(research.router, prefix="/api/pipeline")
app.include_router(memory.router, prefix="/api/memory")

# --- NEW AUTO RESEARCH ROUTER ---
app.include_router(scheduler_router, prefix="/api/schedule")


# -------------------------
# Startup event (NEW)
# -------------------------
@app.on_event("startup")
def startup_event():
    # start the scheduler
    start_scheduler()

    # restore tasks from last session
    restore_jobs_from_disk()


# -------------------------
# Root (unchanged)
# -------------------------
@app.get("/")
def root():
    return {"service": "SIRA", "version": settings.api_version}
