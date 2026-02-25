"""
API FastAPI pour piloter le Job Agent via HTTP.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.agent.orchestrator import JobAgent
from src.tracker.tracker import ApplicationTracker
from src.config import load_criteria, load_profile


# ── State ──────────────────────────────────────────────────────────
agent: JobAgent | None = None
tracker = ApplicationTracker()
is_running = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise l'agent au démarrage."""
    global agent
    agent = JobAgent()
    yield


app = FastAPI(
    title="Job Agent API",
    description="API pour piloter l'agent de candidature automatique",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ─────────────────────────────────────────────────────────
class RunRequest(BaseModel):
    mode: str = "semi-auto"  # "semi-auto" | "full-auto"
    preview: bool = False     # True = scrape + match sans postuler


class StatusUpdate(BaseModel):
    status: str


# ── Routes ─────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "ok", "service": "Job Agent API", "running": is_running}


@app.post("/agent/run")
async def run_agent(request: RunRequest, background_tasks: BackgroundTasks):
    """Lance le pipeline de l'agent."""
    global is_running
    if is_running:
        raise HTTPException(status_code=409, detail="L'agent est déjà en cours d'exécution")

    async def _run():
        global is_running
        is_running = True
        try:
            if request.preview:
                await agent.scrape_only()
            else:
                agent.mode = request.mode
                await agent.run()
        finally:
            is_running = False

    background_tasks.add_task(asyncio.create_task, _run())
    return {"message": "Agent lancé", "mode": request.mode, "preview": request.preview}


@app.get("/agent/status")
async def agent_status():
    """Vérifie si l'agent est en cours d'exécution."""
    return {"running": is_running}


@app.get("/applications")
async def list_applications(status: str | None = None):
    """Liste toutes les candidatures."""
    apps = tracker.get_all_applications(status=status)
    return {"count": len(apps), "applications": apps}


@app.get("/applications/stats")
async def application_stats():
    """Statistiques des candidatures."""
    return tracker.get_stats()


@app.patch("/applications/{app_id}")
async def update_application_status(app_id: int, update: StatusUpdate):
    """Met à jour le statut d'une candidature."""
    from src.models import ApplicationStatus
    try:
        new_status = ApplicationStatus(update.status)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Statut invalide. Valeurs possibles: {[s.value for s in ApplicationStatus]}",
        )
    tracker.update_status(app_id, new_status)
    return {"message": f"Candidature {app_id} mise à jour: {new_status.value}"}


@app.get("/criteria")
async def get_criteria():
    """Retourne les critères de recherche actuels."""
    return load_criteria()


@app.get("/profile")
async def get_profile():
    """Retourne le profil utilisateur (sans données sensibles)."""
    profile = load_profile()
    # Masquer l'email et le téléphone
    identity = profile.get("identite", {})
    if "email" in identity:
        email = identity["email"]
        identity["email"] = email[:3] + "***" + email[email.index("@"):]
    if "telephone" in identity:
        identity["telephone"] = "***masqué***"
    return profile
