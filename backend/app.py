from config import settings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# --- Existing Routers ---
from routers import health, memory, research
from routers.history import router as history_router
from routers.scheduler import router as scheduler_router

# --- Scheduler Services ---
from services.scheduler import cancel_job, restore_jobs_from_db, start_scheduler

app = FastAPI(title="SIRA Backend", version=settings.api_version)

# -------------------------
# CORS
# -------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Routers
# -------------------------
app.include_router(health.router, prefix="/health")
app.include_router(research.router, prefix="/api/pipeline")
app.include_router(memory.router, prefix="/api/memory")
app.include_router(scheduler_router, prefix="/api/schedule")
app.include_router(history_router, prefix="/api/schedule")


# -------------------------
# Startup event
# -------------------------
@app.on_event("startup")
def startup_event():
    start_scheduler()
    restore_jobs_from_db()


# -------------------------
# Root
# -------------------------
@app.get("/")
def root():
    return {"service": "SIRA", "version": settings.api_version}


# -------------------------
# CANCEL JOB ENDPOINT  (FIXED)
# -------------------------
@app.post("/api/schedule/cancel")
def cancel_job_route(job_id: str):
    ok = cancel_job(job_id)
    return {"status": "cancelled", "job_id": job_id, "success": ok}
