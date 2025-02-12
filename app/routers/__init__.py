"""
Router package
"""

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordBearer

from . import groups, permissions, revisions, users
from .public import router as public_router
from .submissions import router as submissions_router

# authentication scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


auth_router = APIRouter(
    prefix="/authorization",
    dependencies=[Depends(oauth2_scheme)],
    responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}},
)

auth_router.include_router(users.router, prefix="/permissions")
auth_router.include_router(groups.router, prefix="/permissions")
auth_router.include_router(permissions.router, prefix="/permissions")

submissions_router.include_router(revisions.router, prefix="/revisions")


__all__ = ["auth_router", "public_router", "submissions_router"]
