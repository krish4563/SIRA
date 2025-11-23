# routers/reports.py
from io import BytesIO

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from services.report_builder import build_job_report

router = APIRouter(tags=["reports"])


@router.get("/generate")
def generate_timeline_report(job_id: str):
    """
    Generate the timeline-style SIRA report (multi-page).
    Uses build_job_report() internally.
    """
    try:
        pdf_bytes = build_job_report(job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[REPORT] Error during PDF generation: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate timeline PDF.")

    filename = f"SIRA_Timeline_{job_id}.pdf"

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
