# routers/reports.py
from io import BytesIO
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

# Import the function we just wrote in services/report.py
from services.report import generate_report_for_conversation

router = APIRouter(tags=["reports"])

@router.get("/conversation/{conversation_id}/download")
def download_conversation_report(conversation_id: str):
    """
    Generate a full PDF report for a conversation and stream it.
    """
    try:
        pdf_bytes = generate_report_for_conversation(conversation_id)
        
        if not pdf_bytes:
             raise HTTPException(status_code=404, detail="Could not generate report (No data found)")

    except Exception as e:
        print(f"[REPORT] Error during PDF generation: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate report.")

    # Create filename based on ID
    filename = f"SIRA_Research_{conversation_id}.pdf"

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )