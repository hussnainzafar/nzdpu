"""radis cache clear"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import Cache, RoleAuthorization
from app.schemas.system import RadisCacheBase

from ..db.models import AuthRole

# pylint: disable = too-many-locals

# creates the router
router = APIRouter(
    prefix="/system",
    tags=["system"],
    responses={404: {"description": "Not found"}},
)


@router.post("/cache/clear", response_model=RadisCacheBase)
async def clear_cache(
    cache: Cache,
    _=Depends(RoleAuthorization([AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR])),
):
    """
    this end point will clear all cache memory
    """
    # Clear the Redis cache
    try:
        # Create a pipeline
        await cache.flushdb()

        return {"success": True, "error_message": ""}

    except Exception as e:
        raise HTTPException(
            status_code=422, detail=f"Failed to clear Redis cache: {str(e)}"
        ) from e
