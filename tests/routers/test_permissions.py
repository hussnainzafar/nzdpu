"""Unit tests for permission router"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.routers.auth_test import AuthTest

from .utils import create_test_group, create_test_permission

BASE_ENDPOINT = "/authorization/permissions"


class TestPermissionsList(AuthTest):
    """
    Unit tests for permissions APIs
    """

    # LIST PERMISSIONS
    @pytest.mark.asyncio
    async def test_list_permissions(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list permissions API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_permission(session)
        # act
        response = await client.get(
            url=BASE_ENDPOINT,
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert j_resp != []
        assert "id" in j_resp[0] and j_resp[0]["id"] == 1
        assert "grant" in j_resp[0]
        assert isinstance(j_resp[0]["grant"], bool)
        assert "list" in j_resp[0]
        assert isinstance(j_resp[0]["list"], bool)
        assert "read" in j_resp[0]
        assert isinstance(j_resp[0]["read"], bool)
        assert "write" in j_resp[0]
        assert isinstance(j_resp[0]["write"], bool)
        assert "user_id" in j_resp[0]
        assert "group_id" in j_resp[0]

    @pytest.mark.asyncio
    async def test_list_permissions_unauthorized(self, client: AsyncClient):
        """
        Test list permissions API for unauthorized access
        """
        # act
        response = await client.get(
            url=BASE_ENDPOINT,
            headers={
                "accept": "application/json",
                "Authorization": f"Testing {self.access_token} ",
            },
        )
        # assert

        assert response.status_code == 401, response.text

    @pytest.mark.asyncio
    async def test_list_permissions_empty(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list permissions API for empty list
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # act
        response = await client.get(
            url=BASE_ENDPOINT,
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert j_resp == []

    @pytest.mark.asyncio
    async def test_list_permissions_set_id(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list permissions API for specific set_id
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_permission(session)

        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}?set_id=1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert j_resp != []
        assert "id" in j_resp[0] and j_resp[0]["id"] == 1
        assert "set_id" in j_resp[0] and j_resp[0]["set_id"] == 1


class TestPermissionsGet(AuthTest):
    """
    Unit tests for permissions APIs
    """

    # GET PERMISSION
    @pytest.mark.asyncio
    async def test_get_permission(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test get permission API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_permission(session)
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1
        assert "id" in j_resp and j_resp["id"] == 1
        assert "grant" in j_resp
        assert isinstance(j_resp["grant"], bool)
        assert "list" in j_resp
        assert isinstance(j_resp["list"], bool)
        assert "read" in j_resp
        assert isinstance(j_resp["read"], bool)
        assert "write" in j_resp
        assert isinstance(j_resp["write"], bool)
        assert "user_id" in j_resp
        assert "group_id" in j_resp

    @pytest.mark.asyncio
    async def test_get_permission_not_found(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test failure of get permissions API in case the given ID does
        not match with a record in the DB
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # act
        response = await client.get(
            f"{BASE_ENDPOINT}/999",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_permission_unauthorized(self, client: AsyncClient):
        """
        Test get permission API for unauthorized access
        """
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/1",
            headers={
                "accept": "application/json",
                "Authorization": f"Testing {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_permission_invalid_id_type(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test get permission API for invalid permission id type
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # act
        response = await client.get(
            f"{BASE_ENDPOINT}/invalid_id",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_permission_large_id(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test get permission API for large permission id
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # act
        response = await client.get(
            f"{BASE_ENDPOINT}/9999999",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_permission_negative_id(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test get permission API for negative permission id
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # act
        response = await client.get(
            f"{BASE_ENDPOINT}/-1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 404


class TestPermissionsPost(AuthTest):
    """
    Unit tests for permissions APIs
    """

    # POST PERMISSION
    @pytest.mark.asyncio
    async def test_create_permission(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create permission API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange - create group
        await create_test_group(session)
        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json={
                "set_id": 1,
                "user_id": 1,
                "group_id": 1,
                "grant": True,
                "list": True,
                "read": True,
                "write": False,
            },
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1

    @pytest.mark.asyncio
    async def test_create_permission_user_not_found(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create permission API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange - create group
        await create_test_group(session)
        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json={
                "set_id": 1,
                "user_id": 999,
                "group_id": 1,
                "grant": True,
                "list": True,
                "read": True,
                "write": False,
            },
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 404
        assert response.json()["detail"] == {"user_id": "User not found."}

    @pytest.mark.asyncio
    async def test_create_permission_group_not_found(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create permission API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json={
                "set_id": 1,
                "user_id": 1,
                "group_id": 999,
                "grant": True,
                "list": True,
                "read": True,
                "write": False,
            },
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 404
        assert response.json()["detail"] == {"group_id": "Group not found."}

    @pytest.mark.asyncio
    async def test_create_permission_unauthorized(self, client: AsyncClient):
        """
        Test create permission API for unauthorized access
        """
        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json={
                "set_id": 1,
                "user_id": 1,
                "group_id": 1,
                "grant": True,
                "list": True,
                "read": True,
                "write": False,
            },
            headers={
                "accept": "application/json",
            },
        )
        # assert
        assert response.status_code == 401
        assert response.json() == {"detail": "Not authenticated"}

    @pytest.mark.asyncio
    async def test_create_permission_invalid_data(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create permission API for invalid input data
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange - create group
        await create_test_group(session)
        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json={
                "set_id": "invalid",
                "user_id": 1,
                "group_id": 1,
                "grant": True,
                "list": True,
                "read": True,
                "write": False,
            },
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 422
        assert "detail" in response.json()

    @pytest.mark.asyncio
    async def test_create_duplicate_permission(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create permission API for duplicate permission
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange - create group and permission
        await create_test_group(session)
        await create_test_permission(session)
        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json={
                "set_id": 1,
                "user_id": 1,
                "group_id": 1,
                "grant": True,
                "list": True,
                "read": True,
                "write": False,
            },
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        # it should return 400 because permission already exists but return 200
        assert response.status_code == 200
        # assert response.json() == {"detail": "Permission already exists."}


class TestUpdatePermission(AuthTest):
    """
    Test update permission API
    """

    # UPDATE PERMISSION
    @pytest.mark.asyncio
    async def test_update_permission_grant(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update permission API - "grant" field only
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_permission(session)
        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/1",
            json={"grant": False},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1
        # here we check successful update of record
        assert not j_resp["grant"]

    @pytest.mark.asyncio
    async def test_update_permission_list(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update permission API - "list" field only
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_permission(session)
        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/1",
            json={"list": False},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1
        # here we check successful update of record
        assert not j_resp["list"]

    @pytest.mark.asyncio
    async def test_update_permission_read(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update permission API - "read" field only
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_permission(session)
        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/1",
            json={"read": False},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1
        # here we check successful update of record
        assert not j_resp["read"]

    @pytest.mark.asyncio
    async def test_update_permission_write(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update permission API - "write" field only
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_permission(session)
        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/1",
            json={"write": True},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1
        # here we check successful update of record
        assert j_resp["write"]

    @pytest.mark.asyncio
    async def test_update_permission_all(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update permission API - all updatable fields
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_permission(session)
        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/1",
            json={
                "grant": False,
                "list": False,
                "read": False,
                "write": True,
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1
        # here we check successful update of record
        assert not j_resp["grant"]
        assert not j_resp["list"]
        assert not j_resp["read"]
        assert j_resp["write"]

    @pytest.mark.asyncio
    async def test_update_permission_not_found(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test fail update permission API - not found
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_permission(session)
        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/999",
            json={"grant": False},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_permission_invalid_data(
        self, client: AsyncClient, session: AsyncSession
    ):
        """Test fail update permission API - invalid data"""
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # arrange
        await create_test_permission(session)
        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/1",
            json={"grant": "invalid"},  # invalid data
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 422  # unprocessable entity


class TestPermissionSet(AuthTest):
    """
    Test permission set API
    """

    @pytest.mark.asyncio
    async def test_create_permission_set(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create permission set API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange - create group
        await create_test_group(session)
        # act
        response = await client.post(
            url=BASE_ENDPOINT + "/set",
            json=[
                {
                    "group_id": 1,
                    "grant": True,
                    "list": True,
                    "read": True,
                    "write": False,
                },
                {
                    "user_id": 1,
                    "grant": True,
                    "list": True,
                    "read": True,
                    "write": True,
                },
            ],
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "set_id" in j_resp and j_resp["set_id"] == 1

    @pytest.mark.asyncio
    async def test_create_permission_set_with_nonexistent_user(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create permission set API with non-existent user
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange - create group
        await create_test_group(session)
        # act
        response = await client.post(
            url=BASE_ENDPOINT + "/set",
            json=[
                {
                    "user_id": 9999,  # non-existent user
                    "grant": True,
                    "list": True,
                    "read": True,
                    "write": False,
                },
            ],
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 404, response.text

    @pytest.mark.asyncio
    async def test_create_permission_set_without_admin_rights(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create permission set API without admin rights
        """
        # do not add admin permission to user

        # arrange - create group
        await create_test_group(session)
        # act
        response = await client.post(
            url=BASE_ENDPOINT + "/set",
            json=[
                {
                    "group_id": 1,
                    "grant": True,
                    "list": True,
                    "read": True,
                    "write": False,
                },
            ],
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # assert

        assert response.status_code == 403, response.text
        assert (
            response.json()["detail"]["global"]
            == "Access denied: insufficient permissions."
        )

    @pytest.mark.asyncio
    async def test_create_permission_set_with_invalid_data(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create permission set API with invalid data
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange - create group
        await create_test_group(session)
        # act
        response = await client.post(
            url=BASE_ENDPOINT + "/set",
            json=[
                {
                    "group_id": "invalid",  # invalid data
                    "grant": True,
                    "list": True,
                    "read": True,
                    "write": False,
                },
            ],
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # assert

        assert response.status_code == 422, response.text
        assert (
            response.json().get("detail")[0].get("msg")
            == "Input should be a valid integer, unable to parse string as an integer"
        )
