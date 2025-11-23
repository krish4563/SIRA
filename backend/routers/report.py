# routers/report.py
# from io import BytesIO

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
from services.report import generate_report_for_job
from services.report_builder import build_job_report

router = APIRouter(tags=["report"])


@router.get("/job/{job_id}/download", response_class=Response)
def download_report(job_id: str):
    """
    Download a SIRA PDF report for a given job_id.
    """
    pdf_bytes = generate_report_for_job(job_id)

    if not pdf_bytes:
        raise HTTPException(
            status_code=404, detail="No report data found for this job_id."
        )

    headers = {
        "Content-Disposition": f'attachment; filename="sira_report_{job_id}.pdf"',
        "Cache-Control": "no-store",
    }

    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


# routers/reports.py


router = APIRouter(tags=["reports"])


@router.get("/generate")
def generate_report(job_id: str):
    """
    Generate a PDF report for a given job_id and stream it as a download.
    """
    try:
        pdf_bytes = build_job_report(job_id)
    except ValueError as e:
        # e.g. not enough history or no job
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Log more detail server-side
        print(f"[REPORT] Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate report.")

    filename = f"SIRA_Report_{job_id}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
