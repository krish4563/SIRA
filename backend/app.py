from config import settings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# --- Routers ---
from routers import health, memory, research
from routers.conversations import router as conversations_router
from routers.history import router as history_router
from routers.report import router as report_router  # Simple report
from routers.reports import router as reports_router  # Timeline report
from routers.scheduler import router as scheduler_router

# --- Scheduler Services ---
from services.scheduler import cancel_job, start_scheduler

app = FastAPI(
    title="SIRA Backend",
    version=settings.api_version,
)

# ----------------------------------------------------
# CORS
# ----------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------
# ROUTERS
# ----------------------------------------------------
app.include_router(health.router, prefix="/health")
app.include_router(research.router, prefix="/api/pipeline")
app.include_router(memory.router, prefix="/api/memory")
app.include_router(scheduler_router, prefix="/api/schedule")
app.include_router(history_router, prefix="/api/schedule")

# PDF report routers (BOTH)
app.include_router(report_router, prefix="/api/report")  # simple report
app.include_router(reports_router, prefix="/api/reports")  # timeline report

app.include_router(conversations_router, prefix="/api/conversations")


# ----------------------------------------------------
# STARTUP
# ----------------------------------------------------
@app.on_event("startup")
def startup_event():
    """
    Start APScheduler and restore DB jobs automatically.
    """
    start_scheduler()


# ----------------------------------------------------
# ROOT
# ----------------------------------------------------
@app.get("/")
def root():
    return {
        "service": "SIRA",
        "version": settings.api_version,
    }


# ----------------------------------------------------
# CANCEL JOB ENDPOINT
# ----------------------------------------------------
@app.post("/api/schedule/cancel")
def cancel_job_route(job_id: str):
    ok = cancel_job(job_id)
    return {
        "status": "cancelled",
        "job_id": job_id,
        "success": ok,
    }
