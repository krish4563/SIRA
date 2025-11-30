# routers/reports.py
from io import BytesIO

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from services.report_builder import build_conversation_report

router = APIRouter(tags=["reports"])


@router.get("/conversation/{conversation_id}/download")
def download_conversation_report(conversation_id: str):
    """
    Generate the timeline-style SIRA report (multi-page) for a conversation
    and stream it as a PDF download.
    """
    try:
        pdf_bytes = build_conversation_report(conversation_id)
    except ValueError as e:
        # e.g. conversation not found
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f"[REPORT] Error during PDF generation: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate report.")

    filename = f"SIRA_Conversation_{conversation_id}.pdf"

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
