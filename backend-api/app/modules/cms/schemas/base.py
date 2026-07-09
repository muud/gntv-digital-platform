"""Schema boundary placeholders for the CMS module."""

from pydantic import BaseModel


class CMSSchemaBase(BaseModel):
    """Base marker for future CMS transport schemas."""
