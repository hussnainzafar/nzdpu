"""
Metric endpoints
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select

from ..db.models import AuthRole, User
from ..dependencies import DbManager, RoleAuthorization
from ..schemas.metrics import ActiveUsersMetricResponse

router = APIRouter(
    prefix="/metrics",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}},
)


@router.get(
    "/users", response_model=ActiveUsersMetricResponse, include_in_schema=False
)
async def get_metrics(
    db_manager: DbManager,
    days: int = 30,
    _=Depends(RoleAuthorization([AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR])),
):
    """
    Retrieve activity metrics.

    :param days: int, optional
        Desired target range in days for measuring activity (e.g., 30, 60, 90 days).
        Defaults to a month (30 days).

    :return: dict
        Activity metrics in the following format:
        {
            "active_users": int,
            "days": int,
            "total_users": int
        }
    """
    lookup_period = datetime.utcnow() - timedelta(days=days)

    async with db_manager.get_session() as session:
        users = select(User)
        total_query = select(func.count()).select_from(users)  # pylint: disable=not-callable
        # pylint: disable=not-callable
        active_users_query = select(func.count()).select_from(
            users.filter(User.last_access >= lookup_period)
        )
        active_count_result = await session.execute(active_users_query)
        total_count_result = await session.execute(total_query)

        return ActiveUsersMetricResponse(
            active_users=active_count_result.scalar_one(),
            total=total_count_result.scalar_one(),
            days=days,
        )
