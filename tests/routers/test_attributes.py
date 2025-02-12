"""Unit tests for attributes router"""

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuthRole
from tests.routers.auth_test import AuthTest

from .utils import create_test_attribute, create_test_table_def


class TestAttributesList(AuthTest):
    """
    Unit tests for attributes APIs
    """

    # LIST ATTRIBUTES
    @pytest.mark.asyncio
    async def test_list_attributes(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list attributes API with pagination
        """
        # arrange
        await create_test_table_def(session)
        for i in range(12):
            await create_test_attribute(session, n=i)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # act
        response = await client.get(
            "/schema/attributes?start=0&limit=10",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "start" in j_resp and j_resp["start"] == 0
        assert "end" in j_resp and j_resp["end"] == 10
        assert "total" in j_resp and j_resp["total"] == 12
        assert "items" in j_resp
        items = j_resp["items"]
        assert isinstance(items, list)
        assert len(items) == 10
        first_item = items[0]
        assert "id" in first_item and first_item["id"] == 1
        assert (
            "attribute_type" in first_item
            and first_item["attribute_type"] == "text"
        )

    @pytest.mark.asyncio
    async def test_list_attributes_empty(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list attributes API when there are no attributes
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # act
        response = await client.get(
            "/schema/attributes?start=0&limit=10",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert not j_resp["items"]

    @pytest.mark.asyncio
    async def test_list_attributes_pagination(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list attributes API with pagination
        """
        # arrange
        await create_test_table_def(session)
        for i in range(20):
            await create_test_attribute(session, n=i)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # act
        response = await client.get(
            "/schema/attributes?start=10&limit=5",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "start" in j_resp and j_resp["start"] == 10
        assert "end" in j_resp and j_resp["end"] == 15
        assert "total" in j_resp and j_resp["total"] == 20
        assert "items" in j_resp
        items = j_resp["items"]
        assert isinstance(items, list)
        assert len(items) == 5

    @pytest.mark.asyncio
    async def test_list_attributes_invalid_params(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list attributes API with invalid parameters
        """

        await self.add_role_to_user(session, AuthRole.ADMIN)

        # act
        response = await client.get(
            "/schema/attributes?start=-1&limit=10",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 422


class TestGetAttributes(AuthTest):
    """
    Unit tests for get attribute API
    """

    # GET ATTRIBUTE
    @pytest.mark.asyncio
    async def test_get_attribute(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test get attribute API
        """
        # arrange
        await create_test_table_def(session)
        await create_test_attribute(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # act
        response = await client.get(
            "/schema/attributes/1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1
        assert "name" in j_resp and j_resp["name"] == "test attribute"
        assert (
            "attribute_type" in j_resp and j_resp["attribute_type"] == "text"
        )

    @pytest.mark.asyncio
    async def test_get_attribute_not_found(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test failure of get attribute API in case the given ID does not
        match with a record in the DB
        """
        # arrange
        await create_test_table_def(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # act
        response = await client.get(
            "/schema/attributes/1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_attribute_unauthorized(self, client: AsyncClient):
        """
        Test failure of get attribute API in case the user is not authorized
        """
        # act
        response = await client.get(
            "/schema/attributes/1",
            headers={
                "accept": "application/json",
            },
        )
        # assert
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_attribute_invalid_id_type(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test failure of get attribute API in case the given ID is not an integer
        """
        # arrange
        await create_test_table_def(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # act
        response = await client.get(
            "/schema/attributes/'invalid'",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_attribute_no_data(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test failure of get attribute API in case there's no data in the DB
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # act
        response = await client.get(
            "/schema/attributes/1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 404


class TestCreateAttribute(AuthTest):
    """
    Unit tests for create attribute API
    """

    # POST ATTRIBUTE
    @pytest.mark.asyncio
    async def test_create_attribute(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create attribute API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_table_def(session)
        # act
        response = await client.post(
            url="/schema/attributes",
            json={
                "name": "test attribute",
                "table_def_id": 1,
                "attribute_type": "text",
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
        assert "table_def_id" in j_resp and j_resp["table_def_id"] == 1
        assert "name" in j_resp and j_resp["name"] == "test attribute"
        assert (
            "attribute_type" in j_resp and j_resp["attribute_type"] == "text"
        )
        assert j_resp["user_id"] == 1

    @pytest.mark.asyncio
    async def test_create_attribute_no_table_def(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create attribute API
        """
        # arrange
        await create_test_table_def(session)
        await self.add_role_to_user(session, AuthRole.SCHEMA_EDITOR)
        # act
        response = await client.post(
            url="/schema/attributes",
            json={"name": "test attribute", "attribute_type": "text"},
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1
        assert j_resp["table_def_id"] is None
        assert "name" in j_resp and j_resp["name"] == "test attribute"
        assert (
            "attribute_type" in j_resp and j_resp["attribute_type"] == "text"
        )

    @pytest.mark.asyncio
    async def test_create_attribute_def_not_found(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test failure of create attribute API when the specified table
        definition does not exist
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_table_def(session)
        # act
        response = await client.post(
            url="/schema/attributes",
            json={
                "name": "test attribute",
                "table_def_id": 999,
                "attribute_type": "text",
            },
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_attribute_duplicated(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test failure of create attribute API when an attribute with the same name already exists in table
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_table_def(session)
        await create_test_attribute(session, name="duplicated")
        # act
        response = await client.post(
            url="/schema/attributes",
            json={
                "name": "duplicated",
                "table_def_id": 1,
                "attribute_type": "text",
            },
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_attribute_unauthorized(self, client: AsyncClient):
        """
        Test failure of create attribute API when the user is not authorized
        """
        # act
        response = await client.post(
            url="/schema/attributes",
            json={
                "name": "test attribute",
                "table_def_id": 1,
                "attribute_type": "text",
            },
            headers={
                "accept": "application/json",
            },
        )
        # assert
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_attribute_invalid_type(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test failure of create attribute API when the attribute type is invalid
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_table_def(session)
        # act
        response = await client.post(
            url="/schema/attributes",
            json={
                "name": "test attribute",
                "table_def_id": 1,
                "attribute_type": "invalid_type",
            },
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_attribute_missing_fields(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test failure of create attribute API when required fields are missing
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_table_def(session)
        # act
        response = await client.post(
            url="/schema/attributes",
            json={},
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 422


class TestUpdateAttribute(AuthTest):
    """
    Test update attribute API
    """

    # UPDATE ATTRIBUTE
    @pytest.mark.asyncio
    async def test_update_attribute(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update attribute API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_table_def(session)
        await create_test_attribute(session)
        # act
        response = await client.patch(
            url="/schema/attributes/1",
            json={"user_id": 1},
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
        assert j_resp["user_id"] == 1

    @pytest.mark.asyncio
    async def test_update_attribute_not_found(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update attribute API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_table_def(session)
        await create_test_attribute(session)
        # act
        response = await client.patch(
            url="/schema/attributes/999",
            json={"active": True},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthorized_update_attribute(self, client: AsyncClient):
        """Test unauthorized update attribute API"""
        # act
        response = await client.patch(
            url="/schema/attributes/1",
            json={"user_id": 1},
            headers={
                "accept": "application/json",
            },
        )
        # assert
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_partial_update_attribute(
        self, client: AsyncClient, session: AsyncSession
    ):
        """Test partial update attribute API"""
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # arrange
        await create_test_table_def(session)
        await create_test_attribute(session)
        # act
        response = await client.patch(
            url="/schema/attributes/1",
            json={"user_id": 1},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 200
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1
        assert j_resp["user_id"] == 1

    @pytest.mark.asyncio
    async def test_update_non_existent_attribute(
        self, client: AsyncClient, session: AsyncSession
    ):
        """Test update non-existent attribute API"""
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # arrange
        await create_test_table_def(session)
        await create_test_attribute(session)
        # act
        response = await client.patch(
            url="/schema/attributes/9999",
            json={"active": True},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 404
