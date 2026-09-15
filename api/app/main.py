from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.dependencies.auth import require_approved_user
from app.errors import register_exception_handlers
from app.logging_config import configure_logging
from app.models.auth import CurrentUser, CurrentUserResponse
from app.routers import (
    assistant,
    artifacts,
    assessments,
    llm,
    production_runs,
    reader,
    stages,
    sources,
    tts,
    wiki,
    workspaces,
)

configure_logging()
settings = get_settings()

app = FastAPI(title="Arsenal API")
register_exception_handlers(app)

def frontend_url(path: str) -> str:
    base = settings.frontend_origins[0].rstrip("/")
    return f"{base}{path}"


@app.get("/", include_in_schema=False)
def redirect_root() -> RedirectResponse:
    return RedirectResponse(url=frontend_url("/app"))


@app.get("/app", include_in_schema=False)
@app.get("/app/{rest:path}", include_in_schema=False)
def redirect_app(rest: str = "") -> RedirectResponse:
    path = f"/app/{rest}" if rest else "/app"
    return RedirectResponse(url=frontend_url(path))


@app.get("/login", include_in_schema=False)
def redirect_login() -> RedirectResponse:
    return RedirectResponse(url=frontend_url("/login"))


@app.get("/auth/callback", include_in_schema=False)
def redirect_auth_callback() -> RedirectResponse:
    return RedirectResponse(url=frontend_url("/auth/callback"))


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(workspaces.router)
app.include_router(stages.router)
app.include_router(sources.router)
app.include_router(production_runs.router)
app.include_router(wiki.router)
app.include_router(reader.router)
app.include_router(artifacts.router)
app.include_router(assessments.router)
app.include_router(llm.router)
app.include_router(tts.router)
app.include_router(assistant.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/me", response_model=CurrentUserResponse)
async def get_me(
    user: Annotated[CurrentUser, Depends(require_approved_user)],
) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
    )
