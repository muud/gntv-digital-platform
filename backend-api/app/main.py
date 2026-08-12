"""Canonical FastAPI application entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, content, health
from app.core.config import settings
from app.core.redis import lifespan
from app.models import audit, auth_extra, user  # noqa: F401
from app.modules.chat.api import router as chat_router
from app.modules.chat.websocket import router as chat_websocket_router
from app.modules.cms.api import content_router
from app.modules.cms.media.api import download_router as media_download_router
from app.modules.cms.media.api import router as media_router
from app.modules.catalog.api import router as catalog_router
from app.modules.editorial.api import router as editorial_router
from app.modules.editorial.tts.api import router as editorial_tts_router
from app.modules.distribution.api import router as distribution_router
from app.modules.streaming.api import router as streaming_router
from app.modules.streaming.api.ingest_router import router as ingest_router
from app.modules.streaming.processing.api import router as processing_router
from app.modules.sheeko_xariiro.api import router as sheeko_xariiro_router


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
app.include_router(media_download_router)
app.include_router(catalog_router)
app.include_router(editorial_router)
app.include_router(editorial_tts_router)
app.include_router(streaming_router)
app.include_router(ingest_router)
app.include_router(processing_router)
app.include_router(distribution_router)
app.include_router(sheeko_xariiro_router)
app.include_router(chat_router)
app.include_router(chat_websocket_router)
