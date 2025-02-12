import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuthRole, Group, Permission
from tests.routers.auth_test import AuthTest
from tests.routers.utils import create_test_group


@pytest.fixture
def group():
    return Group(name="test_group", description="test_group")


class TestPermissionOutputGet(AuthTest):
    @pytest.mark.asyncio
    async def test_get_permission_output(
        self, client: AsyncClient, session: AsyncSession, group
    ):
        session.add(group)
        await session.commit()

        permissions: list[Permission] = [
            Permission(
                set_id=1,
                grant=False,
                list=False,
                read=True,
                write=False,
                group_id=1,
                user_id=1,
                id=0,
            )
        ]
        session.add_all(permissions)
        await session.commit()
        await self.add_role_to_user(session, AuthRole.ADMIN)

        response = await client.get(
            url="/authorization/permissions/0",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp == {
            "set_id": 1,
            "grant": False,
            "list": False,
            "read": True,
            "write": False,
            "group_id": 1,
            "user_id": 1,
            "id": 0,
        }

    @pytest.mark.asyncio
    async def test_list_permissions_output(
        self, client: AsyncClient, session: AsyncSession, group
    ):
        session.add(group)
        await session.commit()

        permissions: list[Permission] = [
            Permission(
                set_id=1,
                grant=False,
                list=False,
                read=True,
                write=False,
                group_id=1,
                user_id=1,
            ),
        ]
        session.add_all(permissions)
        await session.commit()
        await self.add_role_to_user(session, AuthRole.ADMIN)

        response = await client.get(
            url="/authorization/permissions",
            params={"start": 0, "limit": 1},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp[0] == {
            "set_id": 1,
            "grant": False,
            "list": False,
            "read": True,
            "write": False,
            "group_id": 1,
            "user_id": 1,
            "id": 1,
        }


class TestPermissionOutputPost(AuthTest):
    @pytest.mark.asyncio
    async def test_create_permission_output(
        self, client: AsyncClient, session: AsyncSession
    ):
        # add admin permission to user
        await self.add_role_to_user(session, AuthRole.ADMIN)
        await create_test_group(session)

        # act
        response = await client.post(
            url="/authorization/permissions",
            json={
                "set_id": 1,
                "user_id": 1,
                "group_id": 2,
                "grant": False,
                "list": False,
                "read": True,
                "write": False,
            },
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp == {
            "set_id": 1,
            "grant": False,
            "list": False,
            "read": True,
            "write": False,
            "group_id": 2,
            "user_id": 1,
            "id": 1,
        }

    @pytest.mark.asyncio
    async def test_create_permission_set_output(
        self, client: AsyncClient, session: AsyncSession
    ):
        # add admin permission to user
        await self.add_role_to_user(session, AuthRole.ADMIN)
        await create_test_group(session)

        # act
        response = await client.post(
            url="/authorization/permissions/set",
            json=[
                {
                    "set_id": 1,
                    "grant": False,
                    "list": False,
                    "read": True,
                    "write": False,
                    "group_id": 2,
                    "user_id": 1,
                },
                {
                    "set_id": 1,
                    "grant": False,
                    "list": False,
                    "read": True,
                    "write": False,
                    "group_id": 2,
                    "user_id": 1,
                },
            ],
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp == {"set_id": 1}


class TestPermissionOutputPatch(AuthTest):
    @pytest.mark.asyncio
    async def test_update_permission_output(
        self, client: AsyncClient, session: AsyncSession, group
    ):
        session.add(group)
        await session.commit()

        permission: Permission = Permission(
            set_id=1,
            grant=False,
            list=False,
            read=False,
            write=False,
            group_id=1,
            user_id=1,
            id=0,
        )
        session.add(permission)
        await session.commit()
        await self.add_role_to_user(session, AuthRole.ADMIN)

        response = await client.patch(
            url="/authorization/permissions/0",
            json={"grant": False, "list": False, "read": True, "write": True},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp == {
            "set_id": 1,
            "grant": False,
            "list": False,
            "read": True,
            "write": True,
            "group_id": 1,
            "user_id": 1,
            "id": 0,
        }
