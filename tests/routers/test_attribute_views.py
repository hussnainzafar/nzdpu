"""Unit tests for attribute view router"""

import pytest
from fastapi.encoders import jsonable_encoder
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.db.models import AuthRole
from app.schemas.column_view import ColumnViewCreate
from tests.routers.auth_test import AuthTest

from .utils import (
    create_test_attribute,
    create_test_attribute_view,
    create_test_table_def,
    create_test_table_view,
)


class TestAttributeViewsList(AuthTest):
    """
    Unit tests for attribute view APIs
    """

    @pytest.mark.asyncio
    async def test_list_attribute_views_with_admin_permission(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list attribute views API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # setup
        await create_test_table_def(session)
        await create_test_table_view(session)
        await create_test_attribute(session)
        await create_test_attribute_view(session)

        # send request
        response = await client.get(
            "/schema/attribute-views",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert "id" in j_resp[0] and j_resp[0]["id"] == 1
        assert len(j_resp) == 1

    @pytest.mark.asyncio
    async def test_list_attribute_views_with_permission(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list attribute views API
        """
        # create test permissions
        set_id: int = await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # setup
        await create_test_table_def(session)
        await create_test_table_view(session)
        await create_test_attribute(session)
        await create_test_attribute_view(session, permissions_set_id=set_id)

        # send request
        response = await client.get(
            "/schema/attribute-views",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert "id" in j_resp[0] and j_resp[0]["id"] == 1
        assert len(j_resp) == 1

    @pytest.mark.asyncio
    async def test_list_attribute_views_with_no_permission(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list attribute views API
        """
        # setup
        await create_test_table_def(session)
        await create_test_table_view(session)
        await create_test_attribute(session)
        await create_test_attribute_view(session)

        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # send request
        response = await client.get(
            "/schema/attribute-views",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert len(j_resp) == 1

    @pytest.mark.asyncio
    async def test_list_attribute_views_no_data(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list attribute views API when there is no data
        """
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # send request
        response = await client.get(
            "/schema/attribute-views",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert len(j_resp) == 0

    @pytest.mark.asyncio
    async def test_list_attribute_views_unauthenticated(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list attribute views API when user is unauthenticated
        """

        # send request without access token
        response = await client.get(
            "/schema/attribute-views",
            headers={
                "accept": "application/json",
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGetAttributeViews(AuthTest):
    """
    Unit tests for attribute view Get API
    """

    @pytest.mark.asyncio
    async def test_get_attribute_view(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test get attribute view API
        """

        # create test permissions
        set_id: int = await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # setup
        await create_test_table_def(session)
        await create_test_table_view(session)
        await create_test_attribute(session)
        await create_test_attribute_view(session, permissions_set_id=set_id)

        # send request
        response = await client.get(
            "/schema/attribute-views/1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1

    @pytest.mark.asyncio
    async def test_get_attribute_view_not_authorized(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test user not granted permissions to get an attribute view from API
        """

        # setup
        await create_test_table_def(session)
        await create_test_table_view(session)
        await create_test_attribute(session)
        await create_test_attribute_view(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # send request
        response = await client.get(
            "/schema/attribute-views/1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_get_attribute_view_not_found(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test get attribute view API when the attribute view does not exist
        """

        # setup
        await create_test_table_def(session)
        await create_test_table_view(session)
        await create_test_attribute(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # send request
        response = await client.get(
            "/schema/attribute-views/999",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_attribute_view_no_access(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test get attribute view API when the user has no access at all
        """

        # setup
        await create_test_table_def(session)
        await create_test_table_view(session)
        await create_test_attribute(session)
        await create_test_attribute_view(session)

        # send request with a different user's token
        response = await client.get(
            "/schema/attribute-views/1",
            headers={
                "accept": "application/json",
                "Authorization": "Test Token",
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestCreateAttributeViews(AuthTest):
    """
    Unit tests for attribute view Create API
    """

    @pytest.mark.asyncio
    async def test_create_attribute_view(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create attribute view API
        """

        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # setup
        await create_test_table_def(session)
        await create_test_table_view(session)
        await create_test_attribute(session)
        # set attribute view schema
        attribute_view_schema = ColumnViewCreate(
            column_def_id=1, table_view_id=1
        )

        # send request
        response = await client.post(
            url="/schema/attribute-views",
            json=jsonable_encoder(attribute_view_schema.model_dump()),
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1
        assert j_resp["user_id"] == 1

    @pytest.mark.asyncio
    async def test_create_attribute_view_no_admin_permissions(
        self, client: AsyncClient, session: AsyncSession
    ):
        """_summary_

        Args:
            client (AsyncClient): _description_
            session (AsyncSession): _description_
        """
        # setup
        await create_test_table_def(session)
        await create_test_table_view(session)
        await create_test_attribute(session)
        attribute_view_schema = ColumnViewCreate(
            column_def_id=1, table_view_id=1
        )
        # Set group for accessing API but not high enough to access attribute view
        await self.add_role_to_user(session, AuthRole.SCHEMA_EDITOR)

        # send request
        response = await client.post(
            url="/schema/attribute-views",
            json=jsonable_encoder(attribute_view_schema.model_dump()),
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestUpdateAttributeViews(AuthTest):
    """
    Unit tests for attribute view Update API
    """

    @pytest.mark.asyncio
    async def test_update_attribute_view(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update attribute view API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # setup
        await create_test_table_def(session)
        await create_test_table_view(session)
        await create_test_attribute(session)
        await create_test_attribute_view(session)

        # send request
        response = await client.patch(
            url="/schema/attribute-views/1",
            json={"choice_set_id": 2},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1
        assert "choice_set_id" in j_resp and j_resp["choice_set_id"] == 2

    @pytest.mark.asyncio
    async def test_unauthorized_access(self, client: AsyncClient):
        """
        Test update attribute view API for unauthorized access
        """
        # send request without authorization header
        response = await client.patch(
            url="/schema/attribute-views/1",
            json={"choice_set_id": 2},
            headers={"accept": "application/json"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_invalid_attribute_view_id(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update attribute view API for invalid attribute view id
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # setup
        await create_test_table_def(session)
        await create_test_table_view(session)
        await create_test_attribute(session)
        await create_test_attribute_view(session)

        # send request with invalid attribute view id
        response = await client.patch(
            url="/schema/attribute-views/9999",  # non-existent id
            json={"choice_set_id": 2},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_invalid_data_types(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update attribute view API for invalid data types
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # setup
        await create_test_table_def(session)
        await create_test_table_view(session)
        await create_test_attribute(session)
        await create_test_attribute_view(session)

        # send request with invalid data type
        response = await client.patch(
            url="/schema/attribute-views/1",
            json={"choice_set_id": "invalid"},  # invalid data type
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
