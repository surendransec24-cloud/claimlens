import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import backend.models  # Ensures all ORM models are registered
from backend.database import engine, Base, SessionLocal
from backend.config import settings
from backend.api.routes_cases import router as cases_router
from backend.api.routes_evidence import router as evidence_router
from backend.api.routes_history import router as history_router, seed_default_claims_history
from backend.api.routes_auth import router as auth_router
from backend.api.routes_admin import router as admin_router

# Initialize Database tables
Base.metadata.create_all(bind=engine)

# Seed historical records
with SessionLocal() as db:
    seed_default_claims_history(db)

app = FastAPI(
    title="ClaimLens Backend API",
    description="Traceable, Uncertainty-Aware Multi-Agent Claims Investigation Engine with Role-Based Access Control",
    version="1.0.0"
)

# Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    # Production note: In production with TLS termination (e.g., Cloudflare, ALB, Nginx),
    # ensure Strict-Transport-Security (HSTS) is also injected at the ingress layer.
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' http: https: ws: wss:;"
    )
    return response

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(auth_router)
app.include_router(admin_router)
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
