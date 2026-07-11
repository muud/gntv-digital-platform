"""Canonical FastAPI application entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, content, health
from app.core.config import settings
from app.core.redis import lifespan
from app.models import audit, auth_extra, user  # noqa: F401
from app.modules.cms.api import content_router
from app.modules.cms.media.api import router as media_router


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(content.router)
app.include_router(content_router)
app.include_router(media_router)
