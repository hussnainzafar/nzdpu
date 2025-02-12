"""radis cache schemas"""

from typing import Optional

from pydantic import BaseModel

# pylint: disable = too-few-public-methods, unsupported-binary-operation


class RadisCacheBase(BaseModel):
    """
    Base schema for radis cache
    """

    success: Optional[bool] = None
    error_message: Optional[str] = None
