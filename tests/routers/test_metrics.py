"""Metrics Test."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuthRole, User
from app.utils import encrypt_password
from tests.routers.auth_test import AuthTest

USER_QTY = 30


class TestUserMetrics(AuthTest):
    """
    Test user metrics
    """

    @pytest_asyncio.fixture(autouse=True)
    async def create_metric_test_users(
        self, create_test_user, client: AsyncClient, session: AsyncSession
    ):
        await self.create_test_permissions(session)
        await self.add_admin_permissions_to_user(session)
        user_credentials = [
            (str(uuid4()), str(uuid4)) for _ in range(USER_QTY)
        ]
        login_times = [
            datetime.utcnow() - timedelta(days=day) for day in range(USER_QTY)
        ]
        users = []
        for i, cred in enumerate(user_credentials):
            username, password = cred[0], encrypt_password(cred[1])
            access_time = login_times[i]
            users.append(
                User(
                    name=username,
                    first_name="test",
                    last_name="user",
                    email=self.email,
                    password=password,
                    last_access=access_time,
                )
            )
        session.add_all(users)
        await session.commit()

    @pytest.mark.asyncio
    async def test_active_user_metrics_endpoint_with_query_param_returns_ok(
        self, client: AsyncClient, session: AsyncSession
    ):
        days = 2
        response = await client.get(
            f"/metrics/users?days={2}",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("days") == days
        assert data.get("active_users") == days + 1
        assert data.get("total") == USER_QTY + 1

    @pytest.mark.asyncio
    async def test_active_user_metrics_endpoint_with_range_not_specified_returns_ok(
        self, client: AsyncClient, session: AsyncSession
    ):
        response = await client.get(
            "/metrics/users",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("days") == USER_QTY  # default days qty = 30
        assert data.get("active_users") == data.get("total") == USER_QTY + 1

    @pytest.mark.asyncio
    async def test_metrics_not_accessible_by_unknown(
        self, client: AsyncClient, session: AsyncSession
    ):
        response = await client.get(
            url="/metrics/users",
            headers={
                "Authorization": "Bearer FakeToken",
            },
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN, response.text

    @pytest.mark.asyncio
    async def test_metrics_not_accessible_by_user_with_no_groups(
        self, client: AsyncClient, session: AsyncSession
    ):
        token = await self.create_more_users(
            client=client,
            session=session,
            user_name="testnogroup",
            user_pass="testnogroup",
        )
        response = await client.get(
            url="/metrics/users",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_metrics_not_accessible_by_data_explorer(
        self, client: AsyncClient, session: AsyncSession
    ):
        token = await self.create_more_users(
            client=client,
            session=session,
            user_name="testexplorer",
            user_pass="testexplorer",
        )
        await self.add_role_to_user(
            session=session,
            role_name=AuthRole.DATA_EXPLORER,
            user_name="testexplorer",
        )
        response = await client.get(
            url="/metrics/users",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_metrics_not_accessible_by_data_publisher(
        self, client: AsyncClient, session: AsyncSession
    ):
        token = await self.create_more_users(
            client=client,
            session=session,
            user_name="testpublisher",
            user_pass="testpublisher",
        )
        await self.add_role_to_user(
            session=session,
            role_name=AuthRole.DATA_PUBLISHER,
            user_name="testpublisher",
        )
        response = await client.get(
            url="/metrics/users",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_metrics_accessible_by_schema_editor(
        self, client: AsyncClient, session: AsyncSession
    ):
        token = await self.create_more_users(
            client=client,
            session=session,
            user_name="testeditor",
            user_pass="testeditor",
        )
        await self.add_role_to_user(
            session=session,
            role_name=AuthRole.SCHEMA_EDITOR,
            user_name="testeditor",
        )
        response = await client.get(
            url="/metrics/users",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_metrics_accessible_by_admin(
        self, client: AsyncClient, session: AsyncSession
    ):
        response = await client.get(
            url="/metrics/users",
            headers={
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK
