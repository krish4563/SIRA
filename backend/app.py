from fastapi import FastAPI
from sira.routes import router

# Create FastAPI app
app = FastAPI(title="SIRA API", version="0.1.0")

# Include routes from sira/routes.py
app.include_router(router)

# Health check endpoint
@app.get("/health")
def health():
    return {"ok": True}
