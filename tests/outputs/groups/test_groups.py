"""Unit tests for group router"""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.db.models import Group, User
from app.schemas.group import GroupCreate
from tests.routers.auth_test import AuthTest

BASE_ENDPOINT = "/authorization/permissions/groups"


class TestListGroups(AuthTest):
    """
    Unit tests for groups APIs
    """

    async def create_test_group(self, session: AsyncSession, **kwargs):
        """
        Creates a table definition in the DB for testing purposes
        """
        group_schema = GroupCreate(
            name=kwargs["name"],
            description=kwargs["description"],
            delegate_user_id=None,
            delegate_group_id=None,
        )
        group = Group(**group_schema.dict())
        session.add(group)
        await session.commit()
        # LIST GROUPS

    async def create_bulk_users(self, session: AsyncSession, users):
        """
        Create multiple users in bulk
        """

        query = "INSERT INTO wis_user (name, first_name, last_name, email, api_key, password, email_verified) VALUES (:name, :first_name, :last_name, :email, :api_key, :password, :email_verified)"
        values = [
            {
                "name": user.get("name", "usertest"),
                "first_name": user.get("first_name", "Test"),
                "last_name": user.get("last_name", "User"),
                "email": user.get("email", "usertest@insomniacdesign.com"),
                "api_key": str(uuid4()),
                "password": user.get("password", "T3stpassw0rd"),
                "email_verified": False,  # Set a default value for email_verified
            }
            for user in users
        ]

        stmt = insert(User).values(values)
        # Execute the statement
        await session.execute(stmt)

        # Commit the changes
        await session.commit()

    @pytest.mark.asyncio
    async def test_list_groups(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list groups API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/1",
            json={"name": "admin", "description": "Administrators"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # arrange
        group_name = [
            {
                "name": "data_explorer",
                "description": "Data explorers",
            },
            {
                "name": "data_publisher",
                "description": "Data publishers",
            },
            {
                "name": "schema_editor",
                "description": "Schema editors",
            },
        ]
        for each in group_name:
            await self.create_test_group(session, **each)

        # act
        response = await client.get(
            BASE_ENDPOINT,
            params={"order": "asc"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()

        assert j_resp == [
            {
                "name": "admin",
                "description": "Administrators",
                "delegate_user_id": None,
                "delegate_group_id": None,
                "id": 1,
            },
            {
                "name": "data_explorer",
                "description": "Data explorers",
                "delegate_user_id": None,
                "delegate_group_id": None,
                "id": 2,
            },
            {
                "name": "schema_editor",
                "description": "Schema editors",
                "delegate_user_id": None,
                "delegate_group_id": None,
                "id": 4,
            },
            {
                "name": "data_publisher",
                "description": "Data publishers",
                "delegate_user_id": None,
                "delegate_group_id": None,
                "id": 3,
            },
        ]

    @pytest.mark.asyncio
    async def test_create_group(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create group API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # arrange
        group_name = [
            {
                "name": "data_explorer",
                "description": "Data explorers",
            },
            {
                "name": "data_publisher",
                "description": "Data publishers",
            },
            {
                "name": "schema_editor",
                "description": "Schema editors",
            },
        ]
        for each in group_name:
            await self.create_test_group(session, **each)
        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json={
                "name": "test_group",
                "description": "test_group",
                "delegate_user_id": 0,
                "delegate_group_id": 0,
            },
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp == {
            "name": "test_group",
            "description": "test_group",
            "delegate_user_id": 0,
            "delegate_group_id": 0,
            "id": 5,
        }

    @pytest.mark.asyncio
    async def test_get_group(self, client: AsyncClient, session: AsyncSession):
        """
        Test get group API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/1",
            json={"name": "admin", "description": "Administrators"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # act
        response = await client.get(
            f"{BASE_ENDPOINT}/1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp == {
            "name": "admin",
            "description": "Administrators",
            "delegate_user_id": None,
            "delegate_group_id": None,
            "id": 1,
        }

    # UPDATE GROUP
    @pytest.mark.asyncio
    async def test_update_group(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update group API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/1",
            json={
                "name": "admin",
                "description": "Administrator",
                "delegate_user_id": None,
                "delegate_group_id": None,
                "id": 1,
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()

        assert j_resp == {
            "name": "admin",
            "description": "Administrator",
            "delegate_user_id": None,
            "delegate_group_id": None,
            "id": 1,
        }

    # ADD USER TO GROUP
    @pytest.mark.asyncio
    async def test_add_user_to_group(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test add user to group API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        users_to_create = []
        for user in range(1, 27):
            users_to_create.append(
                {
                    "name": f"user{user}",
                    "email": f"user{user}@example.com",
                    "password": "T3stpassw0rd",
                    "first_name": f"Test{user}",
                    "last_name": f"{user}User",
                }
            )

        await self.create_bulk_users(session, users_to_create)

        # arrange
        group_name = [
            {
                "name": "data_explorer",
                "description": "Data explorers",
            }
        ]
        for each in group_name:
            await self.create_test_group(session, **each)

        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/2/add-user?user_id=26",
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        # assert

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()

        assert j_resp == {"success": True}

    @pytest.mark.asyncio
    async def test_remove_user_from_group(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test add user to group API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        users_to_create = []
        for user in range(1, 27):
            users_to_create.append(
                {
                    "name": f"user{user}",
                    "email": f"user{user}@example.com",
                    "password": "T3stpassw0rd",
                    "first_name": f"Test{user}",
                    "last_name": f"{user}User",
                }
            )

        await self.create_bulk_users(session, users_to_create)
        # arrange
        # arrange
        group_name = [
            {
                "name": "data_explorer",
                "description": "Data explorers",
            }
        ]
        for each in group_name:
            await self.create_test_group(session, **each)

        # add user to group
        response = await client.post(
            url=f"{BASE_ENDPOINT}/2/add-user?user_id=26",
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert "success" in j_resp and j_resp["success"] is True

        # remove user from group
        response = await client.post(
            url="/authorization/permissions/groups/2/remove-user?user_id=26",
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()

        j_resp == {"success": True}
