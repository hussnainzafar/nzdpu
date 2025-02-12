"""
Module for public APIs which do not require authentication.
"""

from fastapi import APIRouter, status

from .firebase_actions import router as firebase_actions_router
from .users import router as users_router

router = APIRouter(
    prefix="/public",
    tags=["public"],
    responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}},
)

router.include_router(users_router, prefix="/users")
router.include_router(firebase_actions_router, prefix="/firebase-action")

__all__ = ["router"]
