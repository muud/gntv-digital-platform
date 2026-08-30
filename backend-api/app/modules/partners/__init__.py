"""Partner syndication and secure embed module."""

from app.modules.partners.api import embed_router, partners_router
from app.modules.partners.models import (
    Partner,
    PartnerApiCredential,
    PartnerBranding,
    PartnerContentType,
    PartnerCredentialStatus,
    PartnerDomain,
    PartnerDomainStatus,
    PartnerEmbedEvent,
    PartnerEmbedEventType,
    PartnerEntitlement,
    PartnerEntitlementStatus,
    PartnerStatus,
)
from app.modules.partners.repository import PartnerRepository
from app.modules.partners.service import PartnerSecurityError, PartnerSyndicationService

__all__ = [
    "Partner",
    "PartnerApiCredential",
    "PartnerBranding",
    "PartnerContentType",
    "PartnerCredentialStatus",
    "PartnerDomain",
    "PartnerDomainStatus",
    "PartnerEmbedEvent",
    "PartnerEmbedEventType",
    "PartnerEntitlement",
    "PartnerEntitlementStatus",
    "PartnerRepository",
    "PartnerSecurityError",
    "PartnerStatus",
    "PartnerSyndicationService",
    "embed_router",
    "partners_router",
]
