from pathlib import Path

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.backend.auth.routes import router as auth_router
from app.backend.lifespan import lifespan
from app.backend.routers.chat_router import router as chat_router
from app.backend.routers.document_router import router as document_router
from app.backend.routers.settings_router import router as settings_router
from app.backend.routers.telemetry_router import router as telemetry_router

app = FastAPI(
    title="Research Assistant",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(document_router)
app.include_router(telemetry_router)
app.include_router(settings_router)


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "ok"}


FRONTEND_DIR = Path(__file__).parent.parent / "frontend-react" / "dist"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
