"""Canonical FastAPI application entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, content, health
from app.core.config import settings
from app.core.redis import lifespan
from app.models import audit, auth_extra, user  # noqa: F401
from app.modules.analytics.api import router as analytics_router
from app.modules.chat.api import router as chat_router
from app.modules.chat.websocket import router as chat_websocket_router
from app.modules.monetization.api import router as monetization_router
from app.modules.partners.api import (
    embed_router,
    partner_portal_router,
    partners_router,
)
from app.modules.cms.api import content_router
from app.modules.cms.media.api import download_router as media_download_router
from app.modules.cms.media.api import router as media_router
from app.modules.catalog.api import router as catalog_router
from app.modules.cdn.api import router as cdn_router
from app.modules.editorial.api import router as editorial_router
from app.modules.editorial.tts.api import router as editorial_tts_router
from app.modules.distribution.api import router as distribution_router
from app.modules.streaming.api import router as streaming_router
from app.modules.streaming.api.ingest_router import router as ingest_router
from app.modules.streaming.processing.api import router as processing_router
from app.modules.sheeko_xariiro.api import router as sheeko_xariiro_router
from app.modules.workflows.api import workflow_runs_router, workflows_router
from app.modules.events import models as event_models  # noqa: F401
from app.modules.events.api import (
    dead_letters_router,
    events_router,
    outbound_webhooks_router,
    public_webhooks_router,
    webhook_deliveries_router,
    webhook_sources_router,
)
from app.modules.jobs import models as job_models  # noqa: F401
from app.modules.jobs.api import (
    job_dead_letters_router,
    jobs_router,
    schedules_router,
    workers_router,
)
from app.modules.agents import models as agent_models  # noqa: F401
from app.modules.agents.api import (
    agents_router,
    approval_policies_router,
    approvals_router,
    metrics_router as agent_metrics_router,
    model_policies_router,
    runs_router as agent_runs_router,
    tool_policies_router,
)
from app.modules.autopilot import models as autopilot_models  # noqa: F401
from app.modules.autopilot.api import router as autopilot_router
from app.modules.reliability import models as reliability_models  # noqa: F401
from app.modules.reliability.api import router as reliability_router


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
app.include_router(cdn_router)
app.include_router(analytics_router)
app.include_router(editorial_router)
app.include_router(editorial_tts_router)
app.include_router(streaming_router)
app.include_router(ingest_router)
app.include_router(processing_router)
app.include_router(distribution_router)
app.include_router(monetization_router)
app.include_router(partners_router)
app.include_router(partner_portal_router)
app.include_router(embed_router)
app.include_router(sheeko_xariiro_router)
app.include_router(chat_router)
app.include_router(chat_websocket_router)
app.include_router(workflows_router)
app.include_router(workflow_runs_router)
app.include_router(events_router)
app.include_router(webhook_sources_router)
app.include_router(webhook_deliveries_router)
app.include_router(outbound_webhooks_router)
app.include_router(dead_letters_router)
app.include_router(public_webhooks_router)
app.include_router(jobs_router)
app.include_router(workers_router)
app.include_router(schedules_router)
app.include_router(job_dead_letters_router)
app.include_router(agents_router)
app.include_router(agent_runs_router)
app.include_router(approvals_router)
app.include_router(model_policies_router)
app.include_router(tool_policies_router)
app.include_router(approval_policies_router)
app.include_router(agent_metrics_router)
app.include_router(autopilot_router)
app.include_router(reliability_router)
