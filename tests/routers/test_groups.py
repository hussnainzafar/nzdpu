"""Unit tests for group router"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.routers.auth_test import AuthTest

from .utils import create_test_group

BASE_ENDPOINT = "/authorization/permissions/groups"

firebase = pytest.mark.skipif("not config.getoption('firebase')")


class TestListGroups(AuthTest):
    """
    Unit tests for groups APIs
    """

    # LIST GROUPS
    @pytest.mark.asyncio
    async def test_list_groups(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list groups API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_group(session)

        # act
        response = await client.get(
            BASE_ENDPOINT,
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "id" in j_resp[1] and j_resp[1]["id"] == 2
        assert "name" in j_resp[1] and j_resp[1]["name"] == "test_group"
        assert (
            "description" in j_resp[1]
            and j_resp[1]["description"] == "test_group_desc"
        )

    # TEST FOR EMPTY GROUPS
    @pytest.mark.asyncio
    async def test_empty_groups(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list groups API when no groups are present
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # act
        response = await client.get(
            BASE_ENDPOINT,
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == 200, response.text
        assert response.json() != []

    # TEST FOR UNAUTHORIZED ACCESS
    @pytest.mark.asyncio
    async def test_unauthorized_access(self, client: AsyncClient):
        """
        Test list groups API for unauthorized access
        """
        # act
        response = await client.get(
            BASE_ENDPOINT,
            headers={
                "accept": "application/json",
            },
        )

        # assert
        assert response.status_code == 401, response.text

    # TEST FOR INVALID TOKEN
    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_invalid_token(self, client: AsyncClient):
        """
        Test list groups API with invalid token
        """

        # act
        response = await client.get(
            BASE_ENDPOINT,
            headers={
                "accept": "application/json",
                "Authorization": "Bearer invalid_token",
            },
        )

        # assert
        assert response.status_code == 403, response.text
        j_resp = response.json()
        assert j_resp["detail"] == {
            "global": ("Access denied: insufficient permissions.")
        }


class TestGetGroup(AuthTest):
    """
    Unit tests for groups APIs
    """

    @pytest.mark.asyncio
    async def test_get_group(self, client: AsyncClient, session: AsyncSession):
        """
        Test get group API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_group(session)

        # act
        response = await client.get(
            f"{BASE_ENDPOINT}/2",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 2
        assert "name" in j_resp and j_resp["name"] == "test_group"
        assert (
            "description" in j_resp
            and j_resp["description"] == "test_group_desc"
        )

    @pytest.mark.asyncio
    async def test_get_group_not_found(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test failure of get groups API in case the given ID does not
        match with a record in the DB
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
    async def test_get_group_without_admin_permissions(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test getting a group without admin permissions
        """
        # arrange
        await create_test_group(session)

        # act
        response = await client.get(
            f"{BASE_ENDPOINT}/2",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == 403, response.text

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_get_group_with_invalid_token(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test getting a group with an invalid token
        """
        # arrange
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # create group
        await create_test_group(session)

        # act
        response = await client.get(
            f"{BASE_ENDPOINT}/2",
            headers={
                "accept": "application/json",
                "Authorization": "Bearer invalid_token",
            },
        )

        # assert
        assert response.status_code == 403, response.text
        j_resp = response.json()
        assert j_resp["detail"] == {
            "global": "Access denied: insufficient permissions."
        }

    @pytest.mark.asyncio
    async def test_get_group_no_token_provided(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test getting a group with no token provided
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_group(session)

        # act
        response = await client.get(
            f"{BASE_ENDPOINT}/2",
            headers={
                "accept": "application/json",
            },
        )

        # assert
        assert response.status_code == 401, response.text


class TestCreateGroup(AuthTest):
    """
    Unit tests for groups APIs
    """

    @pytest.mark.asyncio
    async def test_create_group(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create group API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json={
                "name": "test_group",
                "description": "test_group_desc",
                "delegate_user_id": 1,
                "delegate_group_id": 1,
            },
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 2
        assert "name" in j_resp and j_resp["name"] == "test_group"
        assert (
            "description" in j_resp
            and j_resp["description"] == "test_group_desc"
        )

    @pytest.mark.asyncio
    async def test_unauthorized_create_group(self, client: AsyncClient):
        """
        Test create group API for unauthorized access
        """
        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json={
                "name": "test_group",
                "description": "test_group_desc",
                "delegate_user_id": 1,
                "delegate_group_id": 1,
            },
            headers={
                "accept": "application/json",
            },
        )

        # assert
        assert response.status_code == 401, response.text

    # TEST FOR INVALID TOKEN
    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_invalid_token_create_group(self, client: AsyncClient):
        """
        Test create group API with invalid token
        """
        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json={
                "name": "test_group",
                "description": "test_group_desc",
                "delegate_user_id": 1,
                "delegate_group_id": 1,
            },
            headers={
                "accept": "application/json",
                "Authorization": "Bearer invalid_token",
            },
        )

        # assert
        assert response.status_code == 403, response.text
        j_resp = response.json()
        assert j_resp["detail"] == {
            "global": "Access denied: insufficient permissions."
        }

    # TEST FOR MISSING FIELDS
    @pytest.mark.asyncio
    async def test_missing_fields_create_group(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create group API with missing fields
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json={
                "description": "test_group_desc",
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == 422, response.text


class TestUpdateGroup(AuthTest):
    """
    Unit tests for groups APIs
    """

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

        # arrange
        await create_test_group(session)

        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/1",
            json={"name": "new_group_name", "description": "new_group_desc"},
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
        assert j_resp["name"] == "new_group_name"
        assert j_resp["description"] == "new_group_desc"

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_update_group_unauthorized(self, client: AsyncClient):
        """
        Test update group API for unauthorized access
        """
        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/1",
            json={"name": "new_group_name", "description": "new_group_desc"},
            headers={
                "accept": "application/json",
                "Authorization": "Bearer invalid_token",
            },
        )
        # assert
        assert response.status_code == 403, response.text
        j_resp = response.json()
        assert j_resp["detail"] == {
            "global": "Access denied: insufficient permissions."
        }

    @pytest.mark.asyncio
    async def test_update_non_existent_group(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update group API for non-existent group
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/9999",
            json={"name": "new_group_name", "description": "new_group_desc"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 404, response.text


class AddUserToGroup(AuthTest):
    """
    Unit tests for groups APIs
    """

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

        # arrange
        await create_test_group(session)

        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/2/add-user?user_id=1",
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "success" in j_resp and j_resp["success"] is True

    @pytest.mark.asyncio
    async def test_add_user_to_group_already_belongs(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test add user to group API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_group(session)

        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/1/add-user?user_id=1",
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == 409, response.text

    @pytest.mark.asyncio
    async def test_add_user_to_non_existent_group(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test add user to non-existent group API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/999/add-user?user_id=1",
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == 404, response.text

    @pytest.mark.asyncio
    async def test_add_non_existent_user_to_group(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test add non-existent user to group API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_group(session)

        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/2/add-user?user_id=999",
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == 404, response.text

    @pytest.mark.asyncio
    async def test_add_existing_user_to_group(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test add existing user to group API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_group(session)

        # act
        # first, add the user to the group
        response = await client.post(
            url=f"{BASE_ENDPOINT}/2/add-user?user_id=1",
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == 200, response.text

        # then, try to add the same user to the same group again
        response = await client.post(
            url=f"{BASE_ENDPOINT}/2/add-user?user_id=1",
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == 409, response.text

    # REMOVE USER FROM GROUP


class RemoveUserFromGroup(AuthTest):
    """
    Unit tests for groups APIs
    """

    @pytest.mark.asyncio
    async def test_remove_user_from_group(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test add user to group API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_group(session)

        # add user to group
        response = await client.post(
            url=f"{BASE_ENDPOINT}/2/add-user?user_id=1",
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "success" in j_resp and j_resp["success"] is True

        # remove user from group
        response = await client.post(
            url="/authorization/permissions/groups/2/remove-user?user_id=1",
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "success" in j_resp and j_resp["success"] is True

    @pytest.mark.asyncio
    async def test_remove_non_member_from_group(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test removing a user from a group they're not part of
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_group(session)

        # try to remove user from group
        response = await client.post(
            url="/authorization/permissions/groups/2/remove-user?user_id=1",
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == 404, response.text

    @pytest.mark.asyncio
    async def test_remove_user_from_non_existent_group(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test removing a user from a non-existent group
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # try to remove user from non-existent group
        response = await client.post(
            url="/authorization/permissions/groups/999/remove-user?user_id=1",
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == 404, response.text

    @pytest.mark.asyncio
    async def test_remove_non_existent_user_from_group(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test removing a non-existent user from a group
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_group(session)

        # try to remove non-existent user from group
        response = await client.post(
            url="/authorization/permissions/groups/2/remove-user?user_id=999",
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == 404, response.text
