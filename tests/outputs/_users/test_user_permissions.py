"""Unit tests for users router"""

import json
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import AuthRole, User
from app.schemas.user import UserUpdate
from tests.routers.auth_test import AuthTest

firebase = pytest.mark.skipif(
    "not config.getoption('firebase')",
    reason="Use --firebase to perform test.",
)


BASE_URL = "/authorization/permissions"


class TestUsersOutput(AuthTest):
    @property
    def headers(self):
        return {
            "accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }

    @property
    def expected_user_str(self):
        return """
            {
                "id": 2,
                "name": "test-api",
                "first_name": "test-name",
                "last_name": "test-last-name",
                "api_key": "test",
                "email": "test@example.com",
                "enabled": true,
                "created_on": null,
                "last_access": null,
                "external_user_id": null,
                "data_last_accessed": null,
                "organization_name": null,
                "jurisdiction": null,
                "groups":
                    [
                        {
                            "name": "data_explorer",
                            "description": "Data explorers",
                            "delegate_user_id": null,
                            "delegate_group_id": null,
                            "id": 2
                        }
                    ],
                "organization_type": "Financial Institution",
                "organization_id": null,
                "lei": null,
                "auth_mode": "FIREBASE",
                "verification_link": null
            }
        """

    @property
    def update_body_str(self):
        return """
            {
                "id": 26,
                "name": "new-test-name",
                "first_name": "User",
                "last_name": "test-last-name2",
                "api_key": "test2",
                "email": "test2@example.com",
                "enabled": true,
                "created_on": "2023-11-11T16:17:18.233328",
                "last_access": null,
                "external_user_id": "mGq2VXVYoLUO9AZtdpRBrWQ4yPu2",
                "data_last_accessed": "2023-11-11T16:00:12.229492",
                "organization_name": null,
                "jurisdiction": null,
                "groups": [
                    {
                    "name": "data_explorer",
                    "description": "Data explorers",
                    "delegate_user_id": null,
                    "delegate_group_id": null,
                    "id": 2
                    }
                ],
                "organization_type": "Financial Institution",
                "organization_id": null,
                "lei": null,
                "auth_mode": "FIREBASE"
            }
        """

    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, session: AsyncSession):
        await self.add_admin_permissions_to_user(session)

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_user_create_get_one_and_list_responses_match_schema(
        self, client: AsyncClient, session: AsyncSession
    ):
        expected_user = json.loads(self.expected_user_str.encode("utf-8"))
        group_data = {
            "name": "data_explorer",
            "description": "Data explorers",
            "delegate_user_id": None,
            "delegate_group_id": None,
            "id": 2,
        }
        data_input = {
            "name": "test-api",
            "first_name": "test-name",
            "last_name": "test-last-name",
            "api_key": "test",
            "email": "test@example.com",
            "password": "testtesttest123",
            "groups": [group_data],
            "organization_type": "Financial Institution",
        }

        response_create = await client.post(
            url=f"{BASE_URL}/users", json=data_input, headers=self.headers
        )
        response_list = await client.get(
            url=f"{BASE_URL}/users", headers=self.headers
        )
        response_get = await client.get(
            url=f"{BASE_URL}/users/2", headers=self.headers
        )
        response_groups = await client.get(
            url=f"{BASE_URL}/groups", headers=self.headers
        )

        user_create = response_create.json()
        users_list = response_list.json()
        user_get = response_get.json()
        groups_list = response_groups.json()

        id = user_create["id"]
        external_id = user_create["external_user_id"]

        user_in_list_resp = users_list["items"][1]
        group_in_list_resp = groups_list[1]

        for key in (
            "external_user_id",
            "data_last_accessed",
            "created_on",
        ):
            assert user_in_list_resp[key]
            expected_user[key] = user_in_list_resp[key]

        assert user_in_list_resp == expected_user
        assert user_get == expected_user
        assert id and external_id and id != external_id
        assert (
            user_in_list_resp["id"] == id
            and user_in_list_resp["external_user_id"] == external_id
        )
        assert group_in_list_resp == group_data

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_list_inactive_users_output_matches_schema(
        self, client: AsyncClient, session: AsyncSession
    ):
        last_access = datetime.now() - timedelta(days=365 * 2)
        users = [
            User(
                name=str(uuid4()),
                first_name=str(uuid4()),
                last_name=str(uuid4()),
                password="123",
                api_key=str(uuid4()),
                groups=[],
                data_last_accessed=last_access,
            )
            for _ in range(10)
        ]
        session.add_all(users)
        await session.commit()
        response = await client.get(
            f"{BASE_URL}/users/1/inactive",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        response_data = response.json()
        assert response_data[0]["total"] == 10
        for user in response_data[0]["items"]:
            dt = datetime.fromisoformat(user["data_last_accessed"])
            assert dt == last_access

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_create_and_list_standalone_user_output_matches_schema(
        self, client: AsyncClient, session: AsyncSession
    ):
        user_data = {
            "name": "test-api2",
            "first_name": "test-name2",
            "last_name": "test-last-name2",
            "api_key": "test2",
            "email": "test2@example.com",
            "password": "testtesttest1232",
            "groups": [],
            "organization_type": "Financial Institution",
        }

        create_response = await client.post(
            url=f"{BASE_URL}/users", json=user_data, headers=self.headers
        )
        list_response = await client.get(
            url=f"{BASE_URL}/users/standalone", headers=self.headers
        )
        user_create = create_response.json()
        user_list = list_response.json()[0]

        assert user_create["id"]
        assert user_create["external_user_id"]
        assert user_list["enabled"]
        assert user_list["first_name"] == user_data["first_name"]
        assert user_list["last_name"] == user_data["last_name"]
        assert user_list["name"] == user_data["name"]

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_update_user_matches_schema(
        self, client: AsyncClient, session: AsyncSession
    ):
        group_data = {
            "name": "data_explorer",
            "description": "Data explorers",
            "delegate_user_id": None,
            "delegate_group_id": None,
            "id": 2,
        }
        username = "testupdateuser"
        await self.create_more_users(
            client=client,
            session=session,
            user_name=username,
            user_pass="testpass2",
        )
        user_db = await session.execute(
            select(User).where(User.name == username)
        )
        user = user_db.scalar_one()

        update_body = json.loads(self.update_body_str.encode("utf-8"))
        valid_update_body = UserUpdate(**update_body).dict()
        update_response = await client.patch(
            url=f"{BASE_URL}/users/{user.id}",
            json=valid_update_body,
            headers=self.headers,
        )
        response_groups = await client.get(
            url=f"{BASE_URL}/groups", headers=self.headers
        )

        response_dict = update_response.json()
        groups_list = response_groups.json()

        group_in_list_resp = groups_list[1]
        for key, val in valid_update_body.items():
            if (
                key not in ("current_password", "new_password", "groups")
                and response_dict[key]
            ):
                assert response_dict[key] == val
        assert len(response_dict["groups"]) > 0
        assert response_dict["groups"][0] == group_data
        assert group_in_list_resp == group_data

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_admin_revoke_output_matches_schema(
        self, client: AsyncClient, session: AsyncSession
    ):
        username = "testrevokeuser"
        await self.create_more_users(
            client=client,
            session=session,
            user_name=username,
            user_pass="testpass2",
        )
        await self.add_role_to_user(
            session,
            AuthRole.ADMIN,
        )
        user_db = await session.execute(
            select(User)
            .options(selectinload(User.groups))
            .where(User.name == username)
        )
        user = user_db.scalars().first()

        response = await client.post(
            url=f"{BASE_URL}/users/admin-revoke",
            json={"user_id": [user.id]},
            headers=self.headers,
        )
        assert response.json() == {"success": True}

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_delete_user_output_matches_schema(
        self, client: AsyncClient, session: AsyncSession
    ):
        username = "testdeleteuser"
        await self.create_more_users(
            client=client,
            session=session,
            user_name=username,
            user_pass="testpass2",
        )
        await self.add_role_to_user(session, AuthRole.ADMIN, username)
        user_db = await session.execute(
            select(User)
            .options(selectinload(User.groups))
            .where(User.name == username)
        )
        user = user_db.scalars().first()
        delete_response = await client.delete(
            url=f"{BASE_URL}/users/{user.id}",
            headers=self.headers,
        )
        assert delete_response.json() == {"id": user.id, "deleted": True}

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_request_publisher_access_output_matches_schema(
        self, client: AsyncClient, session: AsyncSession
    ):
        request = {
            "role": "string",
            "linkedin_link": None,
            "company_lei": "test-lei",
            "company_type": "string",
            "company_website": None,
        }
        response = await client.post(
            url=f"{BASE_URL}/users/request-publisher-access",
            json=request,
            headers=self.headers,
        )
        assert response.json() == {"status": "requested"}

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_reset_password_response_output_matches_schema(
        self, client: AsyncClient, session: AsyncSession
    ):
        group_data = {
            "name": "data_explorer",
            "description": "Data explorers",
            "delegate_user_id": None,
            "delegate_group_id": None,
            "id": 2,
        }
        data_input = {
            "name": "resetpasswordtest",
            "first_name": "test-name",
            "last_name": "test-last-name",
            "api_key": "test",
            "email": "test@example.com",
            "password": "testtesttest123",
            "groups": [group_data],
            "organization_type": "Financial Institution",
        }

        response_create = await client.post(
            url=f"{BASE_URL}/users", json=data_input, headers=self.headers
        )
        id = response_create.json()["id"]

        response = await client.get(
            url=f"{BASE_URL}/users/{id}/reset-password",
            headers=self.headers,
        )
        response_groups = await client.get(
            url=f"{BASE_URL}/groups", headers=self.headers
        )
        response_dict = response.json()
        groups_list = response_groups.json()
        group_in_list_resp = groups_list[1]

        assert len(response_dict["groups"]) > 0
        assert response_dict["groups"][0] == group_data
        assert group_in_list_resp == group_data

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_notification_signup_output_matches_schema(
        self, client: AsyncClient, session: AsyncSession
    ):
        response = await client.post(
            url=f"{BASE_URL}/users/notifications-signup", headers=self.headers
        )
        assert response.json() == {"user_id": 1, "notifications": True}

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_get_current_user_output_matches_schema(
        self, client: AsyncClient, session: AsyncSession
    ):
        response = await client.get(
            url=f"{BASE_URL}/users/current_user", headers=self.headers
        )
        user_data = response.json()
        assert user_data["id"] == 1
        assert user_data["groups"][0]["name"] == "admin"
        assert user_data["auth_mode"] == "LOCAL"

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_get_access_key_oputput_matches_schema(
        self, client: AsyncClient, session: AsyncSession
    ):
        response = await client.get(
            url=f"{BASE_URL}/users/get-access-key", headers=self.headers
        )
        response_data = response.json()
        assert response_data["access_key"]
