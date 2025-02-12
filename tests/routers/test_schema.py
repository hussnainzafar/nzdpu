"""Unit tests for schema router"""

import json

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette import status

from app import settings
from app.db.models import AuthRole, ColumnDef, TableDef, TableView
from app.schemas.column_def import AttributeType, ColumnDefCreate
from app.schemas.table_def import TableDefCreate
from app.schemas.table_view import TableViewCreate
from tests.routers.auth_test import AuthTest

from .utils import create_test_form

firebase = pytest.mark.skipif("not config.getoption('firebase')")


class TestSchema(AuthTest):
    """
    Unit tests for schema APIs
    """

    data_dir: str = f"{settings.BASE_DIR}/../tests/data"

    @pytest.mark.asyncio
    async def test_list_schemas(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List Schemas" API
        """
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # create test forms
        await create_test_form(f"{self.data_dir}/form-create.json", session)
        await create_test_form(f"{self.data_dir}/nzdpu-scope-1.json", session)

        # send request
        response = await client.get(
            "/schema",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert len(j_resp) == 2

    @pytest.mark.asyncio
    async def test_list_schemas_empty(
        self, client: AsyncClient, session: AsyncSession
    ):
        """_summary_

        Args:
            client (AsyncClient): _description_
            session (AsyncSession): _description_
        """
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        response = await client.get(
            "/schema",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert len(j_resp) == 0

    @pytest.mark.asyncio
    async def test_get_id(self, client: AsyncClient, session: AsyncSession):
        """
        Test "Get ID" API
        """
        # create test table
        test_name: str = "sample_questionnaire"
        test_tab = TableDefCreate(name=test_name)
        table_def = TableDef(**test_tab.dict())
        session.add(table_def)
        await session.commit()

        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # send request
        response = await client.get(
            "/schema/get-id",
            params={"name": test_name},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1

    @pytest.mark.asyncio
    async def test_get_id_schema_not_found(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Get ID" API when the schema does not exist
        """
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # send request for a non-existing schema
        response = await client.get(
            "/schema/get-id",
            params={"name": "non_existing_schema"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_schema(
        self, client: AsyncClient, session: AsyncSession, redis_client
    ):
        """
        Test "Get Schema" API
        """

        # create test form
        schema_path: str = f"{self.data_dir}/form-create.json"
        table_id, _, _ = await create_test_form(schema_path, session)

        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # send request
        response = await client.get(
            "/schema/full",
            params={"table_id": table_id},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()

        # load reference schema
        with open(f"{self.data_dir}/form-get.json", encoding="utf-8") as f_ref:
            j_ref = json.load(f_ref)

        assert all(
            j_resp[key] == j_ref[key]
            for key in ["id", "name", "description", "user_id", "heritable"]
        )
        assert len(j_resp["views"]) == len(j_ref["views"])
        assert len(j_resp["attributes"]) == len(j_ref["attributes"])

    @pytest.mark.asyncio
    async def test_get_schema_invalid_table_id(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Get Schema" API with invalid table_id
        """
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # send request with invalid table_id
        response = await client.get(
            "/schema/full",
            params={"table_id": "invalid"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_get_schema_non_existent_table_id(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Get Schema" API with non-existent table_id
        """
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # send request with non-existent table_id
        response = await client.get(
            "/schema/full",
            params={"table_id": 9999},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_update_schema(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test schema update.

        Creates a new column definition while adding it to the table,
        creates a new column view for it and adds it to the related
        table view, updates a column def already associated to the table
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.SCHEMA_EDITOR)
        # create test table definition
        test_name: str = "sample_questionnaire"
        test_tab = TableDefCreate(name=test_name)  # type: ignore
        table_def = TableDef(**test_tab.model_dump())
        session.add(table_def)
        await session.flush()
        # create test table view
        test_view = TableViewCreate(
            table_def_id=table_def.id,
            name=test_name + "_view",
            active=True,
        )  # type: ignore
        table_view = TableView(**test_view.model_dump())
        session.add(table_view)
        # create test column definition
        test_column = ColumnDefCreate(
            name="test_attribute",
            table_def_id=1,
            attribute_type=AttributeType.INT,
        )  # type: ignore
        column_def = ColumnDef(**test_column.model_dump())
        session.add(column_def)

        await session.commit()
        # act
        response = await client.post(
            url="/schema/1",
            json={
                "add_attributes": [
                    {
                        "name": "test_attribute_2",
                        "attribute_type": AttributeType.TEXT,
                    },
                ],
                "update_attributes": [
                    {"id": 1, "name": "test_attribute_updated"}
                ],
            },
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp["added"] == 1
        assert j_resp["updated"] == 1
        # asserts on elements
        # assert default column view created and assigned to table view
        table_view = await session.scalar(
            select(TableView)
            .where(TableView.id == table_view.id)
            .options(selectinload(TableView.column_views))
        )
        assert table_view.column_views  # type: ignore
        # assert column def updated
        updated_column_def = await session.scalar(
            select(ColumnDef).where(ColumnDef.id == 1)  # type: ignore
        )
        await session.refresh(updated_column_def)
        assert updated_column_def.name == "test_attribute_updated"  # type: ignore
        # assert column def added to table def
        table_def = await session.scalar(
            select(TableDef)
            .where(TableDef.name == test_name)
            .options(selectinload(TableDef.columns))
        )
        assert "test_attribute_2" in [col.name for col in table_def.columns]  # type: ignore

    @pytest.mark.asyncio
    async def test_update_schema_already_added_no_increment(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test schema update.

        Attempts to add a column definition to the table when the column
        is already present, skipping the operation. Shall return added=0
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.SCHEMA_EDITOR)
        # create test table definition
        test_name: str = "sample_questionnaire"
        test_tab = TableDefCreate(name=test_name)  # type: ignore
        table_def = TableDef(**test_tab.dict())
        session.add(table_def)
        await session.flush()
        # create test table view
        test_view = TableViewCreate(
            table_def_id=table_def.id,
            name=test_name + "_view",
            active=True,
        )  # type: ignore
        table_view = TableView(**test_view.dict())
        session.add(table_view)
        # create test column definition
        test_column = ColumnDefCreate(
            name="test_attribute",
            table_def_id=1,
            attribute_type=AttributeType.INT,
        )  # type: ignore
        column_def = ColumnDef(**test_column.dict())
        session.add(column_def)
        await session.commit()
        # act
        response = await client.post(
            url="/schema/1",
            json={
                "add_attributes": [
                    {
                        "name": "test_attribute",
                        "attribute_type": AttributeType.TEXT,
                    },
                ],
            },
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp["added"] == 0
        assert j_resp["updated"] == 0
        # asserts on elements
        # assert column def hasn't changed at all
        column_def = await session.scalar(
            select(ColumnDef).where(ColumnDef.name == "test_attribute")  # type: ignore
        )
        assert column_def.attribute_type == AttributeType.INT

    @pytest.mark.asyncio
    async def test_update_schema_updates_non_existent_column_fails(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test schema update.

        Attempts to update a non-exising column definition. Raises 404.
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.SCHEMA_EDITOR)
        # create test table definition
        test_name: str = "sample_questionnaire"
        test_tab = TableDefCreate(name=test_name)  # type: ignore
        table_def = TableDef(**test_tab.dict())
        session.add(table_def)
        await session.flush()
        # create test table view
        test_view = TableViewCreate(
            table_def_id=table_def.id,
            name=test_name + "_view",
            active=True,
        )  # type: ignore
        table_view = TableView(**test_view.dict())
        session.add(table_view)

        await session.commit()
        # act
        response = await client.post(
            url="/schema/1",
            json={
                "update_attributes": [
                    {"id": 999, "name": "test_attribute_updated"}
                ]
            },
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        # assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        j_resp = response.json()
        assert j_resp["detail"] == {
            "update_attributes": "Attribute not found."
        }

    @pytest.mark.asyncio
    async def test_update_schema_no_attributes(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test schema update.

        Attempts to update a schema without providing any attributes.
        Should return added=0 and updated=0.
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.SCHEMA_EDITOR)
        # create test table definition
        test_name: str = "sample_questionnaire"
        test_tab = TableDefCreate(name=test_name)  # type: ignore
        table_def = TableDef(**test_tab.dict())
        session.add(table_def)
        await session.flush()

        await session.commit()
        # act
        response = await client.post(
            url="/schema/1",
            json={},
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp["added"] == 0
        assert j_resp["updated"] == 0

    @pytest.mark.asyncio
    async def test_update_schema_invalid_attribute_type(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test schema update.

        Attempts to add an attribute with an invalid attribute type.
        Should raise a validation error.
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.SCHEMA_EDITOR)
        # create test table definition
        test_name: str = "sample_questionnaire"
        test_tab = TableDefCreate(name=test_name)  # type: ignore
        table_def = TableDef(**test_tab.model_dump())
        session.add(table_def)
        await session.flush()

        await session.commit()
        # act
        response = await client.post(
            url="/schema/1",
            json={
                "add_attributes": [
                    {
                        "name": "test_attribute",
                        "attribute_type": "INVALID_TYPE",
                    },
                ],
            },
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        # assert
        assert (
            response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        ), response.text

    @pytest.mark.asyncio
    async def test_apply_filtering_by_name(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List Schemas with filtering by name" API
        """

        # create test forms
        await create_test_form(f"{self.data_dir}/form-create.json", session)
        await create_test_form(f"{self.data_dir}/nzdpu-scope-1.json", session)

        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # send request
        response = await client.get(
            '/schema?filter_by={"name":"nzdpu_scope"}',
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert len(j_resp) == 1
        assert "nzd" in j_resp[0]["name"]

    @pytest.mark.asyncio
    async def test_apply_order_by_id_and_name(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List Schemas with order by id and name" API
        """

        # create test forms
        await create_test_form(f"{self.data_dir}/form-create.json", session)
        await create_test_form(f"{self.data_dir}/nzdpu-scope-1.json", session)

        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # send request
        response = await client.get(
            '/schema?order_by=["id","name"]',
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()

        assert len(j_resp) == 2
        assert j_resp[0]["id"] == 1
        assert j_resp[1]["id"] == 2

    @pytest.mark.asyncio
    async def test_apply_order_by_name(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List Schemas with order by name" API
        """

        # create test forms
        await create_test_form(f"{self.data_dir}/form-create.json", session)
        await create_test_form(f"{self.data_dir}/nzdpu-scope-1.json", session)

        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # send request
        response = await client.get(
            '/schema?order_by=["name"]',
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert len(j_resp) == 2
        assert j_resp[0]["name"] == "nzdpu_form"
        assert j_resp[0]["id"] == 1
        assert j_resp[1]["name"] == "nzdpu_scope_1"
        assert j_resp[1]["id"] == 2

    @pytest.mark.asyncio
    async def test_apply_order_by_id_order_desc(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List Schemas with order by id order desc" API
        """

        # create test forms
        await create_test_form(f"{self.data_dir}/form-create.json", session)
        await create_test_form(f"{self.data_dir}/nzdpu-scope-1.json", session)

        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # send request
        response = await client.get(
            '/schema?order_by=["id"]&order=desc',
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert len(j_resp) == 2
        assert j_resp[0]["id"] == 2
        assert j_resp[1]["id"] == 1

    @pytest.mark.asyncio
    async def test_apply_order_not_valid(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List Schemas with order not valid" API
        """

        # create test forms
        await create_test_form(f"{self.data_dir}/form-create.json", session)
        await create_test_form(f"{self.data_dir}/nzdpu-scope-1.json", session)

        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # send request
        response = await client.get(
            '/schema?order_by=["id"]&order=test',
            params={"order_by": "id", "order": "test"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        j_resp = response.json()
        assert (
            j_resp["detail"]
            == "Invalid order value test. Must be 'asc' or 'desc'."
        )

    @pytest.mark.asyncio
    async def test_apply_order_by_not_valid(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List Schemas with order by not valid" API
        """

        # create test forms
        await create_test_form(f"{self.data_dir}/form-create.json", session)
        await create_test_form(f"{self.data_dir}/nzdpu-scope-1.json", session)

        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # send request
        response = await client.get(
            '/schema?order_by=["example"]',
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        j_resp = response.json()
        assert (
            j_resp["detail"] == "Invalid order_by value example."
            " Must be id, name, active or created_on."
        )
