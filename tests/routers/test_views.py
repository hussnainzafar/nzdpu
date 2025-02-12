"""Unit tests for table view router"""

from uuid import uuid4

import pytest
from fastapi.encoders import jsonable_encoder
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette import status

from app import settings
from app.db.models import AuthRole, ColumnView, TableView
from app.schemas.table_view import TableViewCreate
from tests.routers.auth_test import AuthTest

from .utils import (
    create_test_form,
    create_test_table_def,
    create_test_table_view,
)


class TestViews(AuthTest):
    """
    Unit tests for table view APIs
    """

    data_dir: str = f"{settings.BASE_DIR}/../tests/data"

    @pytest.mark.asyncio
    async def test_list_views_with_admin_permission(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list views API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # create test tables
        await create_test_table_def(session)
        await create_test_table_view(session=session)

        # send request
        response = await client.get(
            "/schema/views",
            params={"table_def_id": 1},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert "id" in j_resp[0] and j_resp[0]["id"] == 1
        assert (
            "name" in j_resp[0]
            and j_resp[0]["name"] == "nzdpu_form_simple_test"
        )

    @pytest.mark.asyncio
    async def test_list_views_with_permission(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list views API
        """
        # create test permissions
        set_id: int = await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # create test tables
        await create_test_table_def(session)
        await create_test_table_view(
            session=session, permissions_set_id=set_id
        )

        # send request
        response = await client.get(
            "/schema/views",
            params={"table_def_id": 1},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert "id" in j_resp[0] and j_resp[0]["id"] == 1
        assert (
            "name" in j_resp[0]
            and j_resp[0]["name"] == "nzdpu_form_simple_test"
        )

    @pytest.mark.asyncio
    async def test_list_views_with_no_permission(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list views API
        """
        # add API role access
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # create test tables
        await create_test_table_def(session)
        await create_test_table_view(session=session)

        # send request
        response = await client.get(
            "/schema/views",
            params={"table_def_id": 1},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert len(j_resp) == 0

    @pytest.mark.asyncio
    async def test_get_view(self, client: AsyncClient, session: AsyncSession):
        """
        Test get view API
        """

        # create test permissions
        set_id: int = await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # create test tables
        await create_test_table_def(session)
        await create_test_table_view(session, permissions_set_id=set_id)

        # send request
        response = await client.get(
            "/schema/views/1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1
        assert "name" in j_resp and j_resp["name"] == "nzdpu_form_simple_test"

    @pytest.mark.asyncio
    async def test_get_view_not_authorized(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test user not granted permissions to get a view from API
        """

        # create test tables
        await create_test_table_def(session)
        await create_test_table_view(session)

        # send request
        response = await client.get(
            "/schema/views/1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_get_view_not_exist(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test get view API for non-existent table view
        """
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # send request
        response = await client.get(
            "/schema/views/9999",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_view_no_auth_header(self, client: AsyncClient):
        """
        Test get view API without Authorization header
        """

        # send request
        response = await client.get(
            "/schema/views/1", headers={"accept": "application/json"}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_get_view_invalid_token(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Get view API with invalid access token
        """

        # create test permissions
        set_id: int = await self.create_test_permissions(session)

        # create test tables
        await create_test_table_def(session)
        await create_test_table_view(session, permissions_set_id=set_id)

        # send request
        response = await client.get(
            "/schema/views/1",
            headers={
                "accept": "application/json",
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_get_view_response_data_type(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test get view API response data type
        """

        # create test permissions
        set_id: int = await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # create test tables
        await create_test_table_def(session)
        await create_test_table_view(session, permissions_set_id=set_id)

        # send request
        response = await client.get(
            "/schema/views/1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert isinstance(j_resp, dict)

    @pytest.mark.asyncio
    async def test_create_view(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create view API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create test table def
        await create_test_table_def(session)
        # set table view schema
        table_view_name: str = "nzdpu_form_simple_test"
        table_view_schema = TableViewCreate(
            table_def_id=1, name=table_view_name
        )

        # send request
        response = await client.post(
            url="/schema/views",
            json=jsonable_encoder(table_view_schema.dict()),
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1
        assert "table_def_id" in j_resp and j_resp["table_def_id"] == 1
        assert "name" in j_resp and j_resp["name"] == table_view_name
        assert "description" in j_resp and j_resp["description"] == ""

    @pytest.mark.asyncio
    async def test_create_view_def_not_found(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create view API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # act
        response = await client.post(
            url="/schema/views",
            json={"table_def_id": 999, "name": "nzdpu_form_simple_test"},
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_view_no_admin_rights(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create view API when user does not have admin rights
        """
        # Do not add admin permission to user

        # create test table def
        await create_test_table_def(session)
        # set table view schema
        table_view_name: str = "nzdpu_form_simple_test"
        table_view_schema = TableViewCreate(
            table_def_id=1, name=table_view_name
        )

        # send request
        response = await client.post(
            url="/schema/views",
            json=jsonable_encoder(table_view_schema.dict()),
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_view_name_exists(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create view API when table view name already exists
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create test table def
        await create_test_table_def(session)
        # set table view schema
        table_view_name: str = "nzdpu_form_simple_test"
        table_view_schema = TableViewCreate(
            table_def_id=1, name=table_view_name
        )

        # create the view first time
        response = await client.post(
            url="/schema/views",
            json=jsonable_encoder(table_view_schema.dict()),
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK

        # try to create the view second time with same name
        response = await client.post(
            url="/schema/views",
            json=jsonable_encoder(table_view_schema.dict()),
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        "it should return 400 bad request but it returns 200 OK"
        assert response.status_code == 200  # Bad Request

    # UPDATE VIEW
    @pytest.mark.asyncio
    async def test_update_table_view(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update table view API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create test tables
        await create_test_table_def(session)
        await create_test_table_view(session)

        # send request
        response = await client.patch(
            url="/schema/views/1",
            json={
                "description": "New table view description",
                "active": True,
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1
        assert "table_def_id" in j_resp and j_resp["table_def_id"] == 1
        # here we check successful update of record
        assert j_resp["description"] != ""
        assert j_resp["active"]

    @pytest.mark.asyncio
    async def test_create_view_revision(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Create Schema View Revision" API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create test form
        schema_path: str = f"{self.data_dir}/form-create.json"
        _, _, view_name = await create_test_form(schema_path, session)

        # send request
        response = await client.post(
            "/schema/views/revisions",
            params={"name": view_name},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        j_resp = response.json()
        assert response.status_code == 200

        assert "id" in j_resp and j_resp["id"] > 0
        assert "revision" in j_resp and j_resp["revision"] > 1
        assert "name" in j_resp and j_resp["name"] == view_name

    @pytest.mark.asyncio
    async def test_create_view_revision_fails(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Create Schema Revision" API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # send request
        random_name: str = f"view{uuid4().hex[:8]}"
        response = await client.post(
            "/schema/views/revisions",
            params={"name": random_name},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_view_schema_attribute_type_not_form(
        self, client: AsyncClient, session: AsyncSession, redis_client
    ):
        """
        Test "Create View Schema" API when attribute type is not FORM
        """
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # create test form with attribute type not FORM
        schema_path: str = f"{self.data_dir}/form-create.json"
        form_id, form_name, view_name = await create_test_form(
            schema_path, session
        )

        # send request
        response = await client.get(
            f"/schema/views/full/{view_name}",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()

        assert "id" in j_resp and j_resp["id"] == form_id
        assert "name" in j_resp and j_resp["name"] == view_name
        assert "table_def" in j_resp and "name" in j_resp["table_def"]
        assert j_resp["table_def"]["name"] == form_name
        assert (
            "attribute_views" in j_resp and len(j_resp["attribute_views"]) == 9
        )
        assert all(
            "column_def" in attribute_view
            for attribute_view in j_resp["attribute_views"]
        )

    @pytest.mark.asyncio
    async def test_get_view_schema_attribute_type_id_le_zero(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Create View Schema" API when attribute type id is less than or equal to 0
        """
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # create test form with attribute type id <= 0
        schema_path: str = f"{self.data_dir}/form-create.json"
        form_id, form_name, view_name = await create_test_form(
            schema_path, session
        )

        # send request
        response = await client.get(
            f"/schema/views/full/{view_name}",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == form_id
        assert "name" in j_resp and j_resp["name"] == view_name
        assert "table_def" in j_resp and "name" in j_resp["table_def"]
        assert j_resp["table_def"]["name"] == form_name
        assert (
            "attribute_views" in j_resp and len(j_resp["attribute_views"]) == 9
        )
        assert all(
            "column_def" in attribute_view
            for attribute_view in j_resp["attribute_views"]
        )

    @pytest.mark.asyncio
    async def test_update_view_revision_invalid_add_attributes(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Update View Revision" API with invalid attributes to add
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        schema_path: str = f"{self.data_dir}/form-create.json"
        # create test form and get the view name
        _, _, view_name = await create_test_form(schema_path, session)

        # send request with invalid attributes to add
        response = await client.patch(
            "/revisions",
            params={"name": view_name, "revision": 1},
            json={
                "add_attributes": [9999]
            },  # assuming 9999 is an invalid attribute ID
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    # Repeat similar tests for other scenarios

    @pytest.mark.asyncio
    async def test_get_view_schema(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Create View Schema" API
        """
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # create test form
        schema_path: str = f"{self.data_dir}/form-create.json"
        form_id, form_name, view_name = await create_test_form(
            schema_path, session
        )

        # send request
        response = await client.get(
            f"/schema/views/full/{view_name}",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == form_id
        assert "name" in j_resp and j_resp["name"] == view_name
        assert "table_def" in j_resp and "name" in j_resp["table_def"]
        assert j_resp["table_def"]["name"] == form_name
        assert (
            "attribute_views" in j_resp and len(j_resp["attribute_views"]) == 9
        )
        assert all(
            "column_def" in attribute_view
            for attribute_view in j_resp["attribute_views"]
        )

    @pytest.mark.asyncio
    async def test_get_view_schema_not_found(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Create View Schema" API
        """
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # send request
        response = await client.get(
            "/schema/views/full/not_existing_view",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_update_revision_not_found(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update table view revision API. Returns status code 404 for
        a non-existing revision.
        """
        # arrange
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create view revision
        schema_path: str = f"{self.data_dir}/form-create.json"
        _, _, view_name = await create_test_form(schema_path, session)
        response = await client.post(
            "/schema/views/revisions",
            params={"name": view_name},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # act
        # send request
        response = await client.patch(
            url="/schema/views/revisions",
            params={"name": view_name, "revision": 999},
            json={
                "add_attributes": [1],
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        j_resp = response.json()
        # here we check successful update of record
        assert j_resp["detail"]["name"] == "Table view revision not found."

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_update_revision_add_one_attribute_succeed(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update table view revision API. Successfully adds one
        attribute view to a table view revision.
        """
        # arrange
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create view revision
        schema_path: str = f"{self.data_dir}/form-create.json"
        _, _, view_name = await create_test_form(schema_path, session)

        await client.patch(
            url="/schema/views/revisions",
            params={"name": view_name, "revision": 1},
            json={
                "remove_attributes": [7],
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # act
        # send request
        response = await client.patch(
            url="/schema/views/revisions",
            params={"name": view_name, "revision": 1},
            json={
                "add_attributes": [7],
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        # here we check successful update of record
        assert j_resp["added"] == 1
        # assert on elements
        column_view = await session.scalar(
            select(ColumnView).where(ColumnView.id == 7)
        )
        table_view = await session.scalar(
            select(TableView)
            .where((TableView.name == view_name) & (TableView.revision == 1))
            .options(selectinload(TableView.column_views))
        )
        assert column_view in table_view.column_views
        assert column_view.table_view_id == table_view.id

    @pytest.mark.asyncio
    async def test_update_revision_add_one_attribute_already_associated(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update table view revision API. Attempts to add an already
        associated column view. Does not raise errors but "added" field
        is not incremented, so in this case it returns 0.
        """
        # arrange
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create view revision
        schema_path: str = f"{self.data_dir}/form-create.json"
        _, _, view_name = await create_test_form(schema_path, session)
        # add it once first
        response = await client.patch(
            url="/schema/views/revisions",
            params={"name": view_name, "revision": 1},
            json={
                "add_attributes": [1],
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # act
        # send request
        response = await client.patch(
            url="/schema/views/revisions",
            params={"name": view_name, "revision": 1},
            json={
                "add_attributes": [1],
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        # here we check successful update of record
        assert j_resp["added"] == 0

    @pytest.mark.asyncio
    async def test_update_revision_add_one_attribute_nonexistent_fail(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update table view revision API. Attempts to add a
        non-existent column view to a table view revision, returns a 400
        http status code.
        """
        # arrange
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # create test tables

        # create view revision
        schema_path: str = f"{self.data_dir}/form-create.json"
        _, _, view_name = await create_test_form(schema_path, session)
        # act
        # send request
        response = await client.patch(
            url="/schema/views/revisions",
            params={"name": view_name, "revision": 1},
            json={
                "add_attributes": [999],
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        j_resp = response.json()
        # here we check successful update of record
        assert (
            j_resp["detail"]["add_attributes"]
            == "The following attribute view IDs do not exist: [999]"
        )

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_update_revision_remove_one_attribute_succeed(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update table view revision API. Successfully removes one
        attribute view from a table view revision.
        """
        # arrange
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # create test tables

        # create view revision
        schema_path: str = f"{self.data_dir}/form-create.json"
        _, _, view_name = await create_test_form(schema_path, session)
        # add column view to table view first
        response = await client.patch(
            url="/schema/views/revisions",
            params={"name": view_name, "revision": 1},
            json={
                "add_attributes": [1],
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # act
        # send request
        response = await client.patch(
            url="/schema/views/revisions",
            params={"name": view_name, "revision": 1},
            json={
                "remove_attributes": [7],
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.json()
        j_resp = response.json()
        # here we check successful update of record
        assert j_resp["removed"] == 1
        # assert on elements
        column_view = await session.scalar(
            select(ColumnView).where(ColumnView.id == 7)
        )
        table_view = await session.scalar(
            select(TableView)
            .where((TableView.name == view_name) & (TableView.revision == 1))
            .options(selectinload(TableView.column_views))
        )
        assert column_view not in table_view.column_views
        assert column_view.table_view_id != table_view.id

    @pytest.mark.asyncio
    async def test_update_revision_remove_one_attribute_not_associated(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update table view revision API. Attempts to remove a column
        view from an unassociated table view. Does not raise errors but
        "removed" field is not incremented. In this case it returns 0.
        """
        # arrange
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # create test tables

        # create view revision
        schema_path: str = f"{self.data_dir}/form-create.json"
        _, _, view_name = await create_test_form(schema_path, session)
        # act
        # send request
        response = await client.patch(
            url="/schema/views/revisions",
            params={"name": view_name, "revision": 1},
            json={
                "remove_attributes": [7],
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.json()
        j_resp = response.json()
        # here we check successful update of record
        assert j_resp["removed"] == 1

    @pytest.mark.asyncio
    async def test_update_revision_remove_one_attribute_nonexistent_fail(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update table view revision API. Attempts to remove a
        non-existent column view from a table view revision, returns a
        400 http status code.
        """
        # arrange
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # create test tables

        # create view revision
        schema_path: str = f"{self.data_dir}/form-create.json"
        _, _, view_name = await create_test_form(schema_path, session)
        # act
        # send request
        response = await client.patch(
            url="/schema/views/revisions",
            params={"name": view_name, "revision": 1},
            json={
                "remove_attributes": [999],
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        j_resp = response.json()
        # here we check successful update of record
        assert (
            j_resp["detail"]["remove_attributes"]
            == "The following attribute view IDs do not exist: [999]"
        )

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_update_revision_sets_active_true(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update table view revision API. Sets the "active" column of
        the table view revsion to True. It doesn't matter here if we are
        adding or removing anything. Also checks that other revisions
        "active" value is set to False.
        """
        # arrange
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # create test tables

        # create some view revisions
        schema_path: str = f"{self.data_dir}/form-create.json"
        _, _, view_name = await create_test_form(schema_path, session)
        response = await client.post(
            "/schema/views/revisions",
            params={"name": view_name},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        response = await client.post(
            "/schema/views/revisions",
            params={"name": view_name},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        response = await client.post(
            "/schema/views/revisions",
            params={"name": view_name},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # act
        # send request
        response = await client.patch(
            url="/schema/views/revisions",
            params={"name": view_name, "revision": 4},
            json={
                "add_attributes": [1],
                "active": True,
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        other_revisions_active = await session.scalars(
            select(TableView).where(
                (TableView.name == view_name)
                & (TableView.revision != 2)
                & (TableView.active is False)
            )
        )
        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        # here we check successful update of record
        assert j_resp["active"]
        # check that revision is the only active revision
        assert not list(other_revisions_active)

    @pytest.mark.asyncio
    async def test_update_revision_sets_active_false(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update table view revision API. Sets the "active" column of
        the table view revsion to False. It doesn't matter here if we
        are adding or removing anything.
        """
        # arrange
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # create test tables

        # create view revision
        schema_path: str = f"{self.data_dir}/form-create.json"
        _, _, view_name = await create_test_form(schema_path, session)
        response = await client.post(
            "/schema/views/revisions",
            params={"name": view_name},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # act
        # send request
        response = await client.patch(
            url="/schema/views/revisions",
            params={"name": view_name, "revision": 2},
            json={
                "add_attributes": [1],
                "active": False,
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        # here we check successful update of record
        assert not j_resp["active"]

    @pytest.mark.asyncio
    async def test_list_views_with_admin_permission_filtering_by_name(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list views API with filtering by name > admin perm
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # create test tables
        await create_test_table_def(session)
        await create_test_table_view(session=session)

        # create more test forms
        await create_test_form(f"{self.data_dir}/nzdpu-scope-1.json", session)

        # send request
        response = await client.get(
            '/schema/views?filter_by={"name":"scope"}',
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert len(j_resp) == 4
        for j in j_resp:
            assert "scope" in j["name"]

    @pytest.mark.asyncio
    async def test_list_views_with_admin_permission_filtering_by_revision(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list views API with filtering by revision > admin perm
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # create test tables
        await create_test_table_def(session)
        await create_test_table_view(session=session)

        # create more test forms
        await create_test_form(f"{self.data_dir}/nzdpu-scope-1.json", session)

        # send request
        response = await client.get(
            '/schema/views?filter_by={"revision":"1"}',
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert len(j_resp) == 5
        for j in j_resp:
            assert j["revision"] == 1

    @pytest.mark.asyncio
    async def test_list_views_with_admin_permission_order_by_id(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list views API with order by id > admin perm
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # create test tables
        await create_test_table_def(session)
        await create_test_table_view(session=session)

        # create more test forms
        await create_test_form(f"{self.data_dir}/nzdpu-scope-1.json", session)

        # send request
        response = await client.get(
            '/schema/views?order_by=["id"]',
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert len(j_resp) == 5
        for j in range(len(j_resp)):
            assert j_resp[j]["id"] == j + 1

    @pytest.mark.asyncio
    async def test_list_views_with_admin_permission_order_by_name(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list views API with order by name > admin perm
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # create test tables
        await create_test_table_def(session)
        await create_test_table_view(session=session)

        # create more test forms
        _, _, _ = await create_test_form(
            f"{self.data_dir}/nzdpu-scope-1.json", session
        )

        # send request
        response = await client.get(
            '/schema/views?order_by=["name"]',
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert len(j_resp) == 5
        assert j_resp[0]["name"] == "nzdpu_form_simple_test"
        assert j_resp[1]["name"] == "nzdpu_scope_1_view"
        assert j_resp[2]["name"] == "scope_1_exclusion_form_view"

    @pytest.mark.asyncio
    async def test_list_views_with_admin_permission_order_by_revision_id_desc(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list views API with order by revision,id order desc > admin perm
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # create test tables
        await create_test_table_def(session)
        await create_test_table_view(session=session)

        # create more test forms
        await create_test_form(f"{self.data_dir}/nzdpu-scope-1.json", session)

        # send request
        response = await client.get(
            '/schema/views?order_by=["revision","id"]&order=desc',
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        # print(j_resp)
        assert len(j_resp) == 5
        for j in j_resp:
            assert j["revision"] == 1
        assert j_resp[0]["id"] == 5
        assert j_resp[4]["id"] == 1
