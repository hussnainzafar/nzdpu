"""Tracking schemas"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import (
    BaseModel,
)

from ..db.models import SourceEnum


class TrackingUrls(str, Enum):
    SEARCH_DOWNLOAD = "/search/download"
    SEARCH_DOWNLOAD_ALL = "/search/download-all"
    SEARCH_DOWNLOAD_SELECTED = "/search/download-selected"
    COMPANIES_HISTORY = "/coverage/companies/{nz_id}/history/download"

    def format_nz_id(self, **kwargs) -> str:
        """
        Format the URL with the provided
        keyword arguments for companies history.
        """
        return self.value.format(**kwargs)


class TrackingBase(BaseModel):
    """
    Base schema for Tracking
    """

    user_email: Optional[str] = None
    api_endpoint: Optional[str] = None
    date_time: datetime = datetime.now()
    source: Optional[SourceEnum] = None
    result: Optional[int] = None


class TrackingCreate(TrackingBase):
    """
    Create schema for Submission
    """
