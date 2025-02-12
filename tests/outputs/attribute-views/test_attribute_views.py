"""Unit tests for attribute view output"""

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app import settings
from app.db.models import ColumnDef, ColumnView, TableDef, TableView
from app.schemas.column_def import AttributeType
from app.schemas.column_view import ColumnViewCreate
from app.schemas.constraint import Constraint
from tests.constants import SCHEMA_FILE_NAME
from tests.routers.auth_test import AuthTest
from tests.routers.utils import create_test_form


class TestAttributeViews(AuthTest):
    """
    Unit tests for attribute view APIs
    """

    provided_values = {
        "code": "string",
        "conditions": [],
        "actions": [{"set": {}}],
    }
    instance = Constraint(**provided_values)

    data_dir: str = f"{settings.BASE_DIR}/../tests/data"

    async def create_test_attribute_view(
        self, session: AsyncSession, permissions_set_id: int = 0
    ):
        """
        Creates an attribute view in the DB for testing purposes
        """
        table_def = TableDef(id=0, name="table_def")

        session.add(table_def)
        await session.flush()

        column_def = ColumnDef(
            id=0,
            table_def_id=table_def.id,
            name="column",
            attribute_type=AttributeType.INT,
        )

        table_view = TableView(
            id=0, table_def_id=table_def.id, name="table_view", revision=1
        )

        session.add_all([column_def, table_view])
        await session.flush()

        attribute_view_schema = ColumnViewCreate(
            column_def_id=column_def.id,
            table_view_id=table_view.id,
            constraint_view="string",
        )

        if permissions_set_id > 0:
            attribute_view_schema.permissions_set_id = permissions_set_id
        attribute_view_schema.constraint_value = [self.instance]

        attribute_view = ColumnView(**attribute_view_schema.model_dump())
        session.add(attribute_view)
        await session.commit()

    @pytest.mark.asyncio
    async def test_list_attribute_views(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list attribute views API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        await self.create_test_attribute_view(session)
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
        j_resp = j_resp[-1]

        assert j_resp["column_def_id"] == 0
        assert j_resp["table_view_id"] == 0
        assert j_resp["constraint_value"] == [self.instance.model_dump()]
        assert datetime.fromisoformat(j_resp["created_on"])
        assert j_resp["constraint_view"] == "string"

    # create attribute view
    @pytest.mark.asyncio
    async def test_create_attribute_view(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create attribute view API
        """
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        attribute_view_schema = {
            "column_def_id": 1053,
            "table_view_id": 58,
            "user_id": 1,
            "permissions_set_id": 0,
            "constraint_value": [
                {"code": "string", "conditions": [], "actions": [{"set": {}}]}
            ],
            "constraint_view": "string",
            "choice_set_id": 0,
        }
        # send request

        response = await client.post(
            url="/schema/attribute-views",
            json=attribute_view_schema,
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()

        assert j_resp["column_def_id"] == 1053
        assert j_resp["table_view_id"] == 58
        assert j_resp["user_id"] == 1
        assert j_resp["permissions_set_id"] == 0
        assert j_resp["constraint_value"] == [self.instance.model_dump()]
        assert datetime.fromisoformat(j_resp["created_on"])
        assert j_resp["constraint_view"] == "string"
        assert j_resp["choice_set_id"] == 0
        assert j_resp["id"] == 1257

    # get attribute view
    @pytest.mark.asyncio
    async def test_get_attribute_view(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create attribute view API
        """
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        attribute_view_schema = {
            "column_def_id": 1053,
            "table_view_id": 58,
            "user_id": 1,
            "permissions_set_id": 0,
            "constraint_value": [
                {"code": "string", "conditions": [], "actions": [{"set": {}}]}
            ],
            "constraint_view": "string",
            "choice_set_id": 0,
        }
        # send request

        response = await client.post(
            url="/schema/attribute-views",
            json=attribute_view_schema,
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK

        # get request to check if the attribute view is created
        # send request
        response = await client.get(
            "/schema/attribute-views/1257",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert j_resp["column_def_id"] == 1053
        assert j_resp["table_view_id"] == 58
        assert j_resp["user_id"] == 1
        assert j_resp["permissions_set_id"] == 0
        assert j_resp["constraint_value"] == [self.instance.model_dump()]
        assert datetime.fromisoformat(j_resp["created_on"])
        assert j_resp["constraint_view"] == "string"
        assert j_resp["choice_set_id"] == 0
        assert j_resp["id"] == 1257

    # update attribute view
    @pytest.mark.asyncio
    async def test_update_attribute_view(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        test suite for update attribute view
        """
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        provided_values = {
            "code": "new_attribute_view",
            "conditions": [],
            "actions": [{"set": {}}],
        }
        instance = Constraint(**provided_values)
        response = await client.patch(
            url="/schema/attribute-views/1052",
            json={
                "column_def_id": 1052,
                "table_view_id": 58,
                "created_on": "2023-10-31T22:48:58.287478",
                "user_id": 1,
                "permissions_set_id": 0,
                "constraint_value": [
                    {
                        "code": "new_attribute_view",
                        "conditions": [],
                        "actions": [{"set": {}}],
                    }
                ],
                "constraint_view": "string",
                "choice_set_id": 0,
                "id": 1052,
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()

        assert j_resp["column_def_id"] == 1052
        assert j_resp["table_view_id"] == 58
        assert j_resp["user_id"] == 1
        assert j_resp["permissions_set_id"] == 0
        assert j_resp["constraint_value"] == [instance.model_dump()]
        assert datetime.fromisoformat(j_resp["created_on"])
        assert j_resp["constraint_view"] == "string"
        assert j_resp["choice_set_id"] == 0
        assert j_resp["id"] == 1052
