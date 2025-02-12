"""Unit tests for schema output"""

import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app import settings
from app.db.models import AuthRole, TableDef
from app.schemas.table_def import TableDefCreate
from tests.constants import SCHEMA_FILE_NAME
from tests.routers.auth_test import AuthTest
from tests.routers.utils import create_test_form


class TestSchema(AuthTest):
    """
    Unit tests for schema APIs
    """

    data_dir: str = f"{settings.BASE_DIR}/../tests/data"

    @staticmethod
    async def create_table_def(session: AsyncSession, tables_data=[]):
        tables: list[TableDefCreate] = [
            TableDefCreate(
                name=each["name"],
                description=each["description"],
                user_id=each["user_id"],
            )
            for each in tables_data
        ]

        for table_def_create in tables:
            table_def = TableDef(**table_def_create.dict())
            session.add(table_def)
            await session.commit()

    @pytest.mark.asyncio
    async def test_list_schemas(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List Schemas" API
        """
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        tables_data = [
            {"name": "test-table", "description": "new", "user_id": 1},
        ]
        await self.create_table_def(session, tables_data)
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

        assert j_resp[0]["name"] == "nzdpu_form"
        assert j_resp[0]["description"] == "NZDPU SCHEMA 4.0"
        assert j_resp[0]["heritable"] == False
        assert j_resp[0]["user_id"] == 1
        assert j_resp[0]["id"] == 1

        assert j_resp[1]["name"] == "test-table"
        assert j_resp[1]["description"] == "new"
        assert j_resp[1]["heritable"] == False
        assert j_resp[1]["user_id"] == 1
        assert j_resp[1]["id"] == 61

    @pytest.mark.asyncio
    async def test_get_id(self, client: AsyncClient, session: AsyncSession):
        """
        Test "Get ID" API
        """

        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        tables_data = [
            {"name": "test-table", "description": "new", "user_id": None},
        ]
        await self.create_table_def(session, tables_data)
        # send request
        response = await client.get(
            "/schema/get-id",
            params={"name": "test-table"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert j_resp == {"id": 61}

    @pytest.mark.asyncio
    async def test_get_schema_full(
        self, client: AsyncClient, session: AsyncSession, redis_client
    ):
        """
        Test "Get Schema" API
        """

        # create test form
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # send request
        response = await client.get(
            "/schema/full",
            params={"table_id": 1},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        # load reference schema

        # USE ME IF NEED TO REBUILD THE RESPONSE
        # with open(
        #     f"{self.data_dir}/form-get_response.json",
        #     "w",
        #     encoding="utf-8",
        # ) as f:
        #     resp = json.dumps(j_resp, indent=4, default=str)
        #     f.write(resp)

        with open(
            f"{self.data_dir}/form-get_response.json", encoding="utf-8"
        ) as f_ref:
            j_ref = json.load(f_ref)
        assert all(
            j_resp[key] == j_ref[key]
            for key in ["id", "name", "description", "user_id", "heritable"]
        )
        assert len(j_resp["views"]) == len(j_ref["views"])
        assert len(j_resp["attributes"]) == len(j_ref["attributes"])

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
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        # act
        response = await client.post(
            url="/schema/1",
            json={
                "add_attributes": [],
                "update_attributes": [
                    {
                        "name": "reporting__datetime",
                        "table_def_id": 1,
                        "created_on": "2023-11-09T10:55:04.842734",
                        "user_id": 1,
                        "attribute_type": "datetime",
                        "attribute_type_id": None,
                        "choice_set_id": None,
                        "id": 1,
                        "choices": None,
                        "prompts": [
                            {
                                "column_def_id": 2,
                                "value": "Reporting date",
                                "description": "",
                                "language_code": "en_US",
                                "role": "label",
                                "id": 2,
                            }
                        ],
                        "form": None,
                        "views": [
                            {
                                "column_def_id": 2,
                                "table_view_id": 1,
                                "created_on": "2023-11-09T10:57:04.843385",
                                "user_id": 1,
                                "permissions_set_id": None,
                                "constraint_value": [],
                                "constraint_view": {
                                    "type": "datetime",
                                    "nzdpuForm": "DISCLOSURE_METADATA",
                                    "view": ["COMPANY_PROFILE"],
                                },
                                "choice_set_id": None,
                                "id": 1,
                                "choices": None,
                            }
                        ],
                    }
                ],
            },
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp == {"added": 0, "updated": 1}
