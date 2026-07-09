"""Shared CMS schema primitives."""

from pydantic import BaseModel, ConfigDict


class CMSSchemaBase(BaseModel):
    """Base class for CMS transport schemas."""

    model_config = ConfigDict(from_attributes=True)
