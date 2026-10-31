import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from backend.database import engine, Base, SessionLocal
from backend.config import settings
from backend.api.routes_cases import router as cases_router
from backend.api.routes_evidence import router as evidence_router
from backend.api.routes_history import router as history_router, seed_default_claims_history

# Initialize Database tables
Base.metadata.create_all(bind=engine)

# Seed historical records
with SessionLocal() as db:
    seed_default_claims_history(db)

app = FastAPI(
    title="ClaimLens Backend API",
    description="Traceable, Uncertainty-Aware Multi-Agent Claims Investigation Engine",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cases_router)
app.include_router(evidence_router)
app.include_router(history_router)

frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))

@app.get("/")
def serve_index():
    index_file = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "ClaimLens API is running. Frontend index.html not found."}

@app.get("/workbench.js")
def serve_js():
    js_file = os.path.join(frontend_dir, "workbench.js")
    if os.path.exists(js_file):
        return FileResponse(js_file, media_type="application/javascript")
    return {"message": "workbench.js not found."}

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "ClaimLens",
        "gemini_model": settings.GEMINI_MODEL,
        "database": settings.DATABASE_URL
    }
