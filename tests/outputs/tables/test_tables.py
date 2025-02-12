"""Unit tests for tables router"""

import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app import settings
from app.db.models import AuthRole
from app.service.core.cache import CoreMemoryCache
from tests.constants import SCHEMA_FILE_NAME
from tests.routers.auth_test import AuthTest
from tests.routers.utils import create_test_form


class TestTables(AuthTest):
    """
    Unit tests for tables APIs
    """

    data_dir: str = f"{settings.BASE_DIR}/../tests/data"

    @pytest.mark.asyncio
    @pytest.mark.order(1)
    async def test_list_tables(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
    ):
        """
        Test "List tables" API
        """
        await static_cache.refresh_values()
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # send request
        response = await client.get(
            "/schema/tables",
            params={"order": "asc"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()

        # USE ME IF NEED TO REBUILD THE RESPONSE
        # with open(
        #     f"{settings.BASE_DIR}/../tests/outputs/tables/data/response_test.json",
        #     "w",
        #     encoding="utf-8",
        # ) as file_resp:
        #     resp = json.dumps(j_resp, indent=4, default=str)
        #     file_resp.write(resp)

        with open(
            f"{settings.BASE_DIR}/../tests/outputs/tables/data/response_test.json",
            encoding="utf-8",
        ) as file_resp:
            file_resp = json.load(file_resp)

        assert all(
            all(
                j_dict[key] == file_dict[key]
                for key in [
                    # "id",
                    # "name",
                    "description",
                    "user_id",
                    "heritable",
                ]
            )
            for j_dict, file_dict in zip(j_resp, file_resp)
        )

    @pytest.mark.asyncio
    async def test_create_table(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List tables" API
        """
        await self.add_admin_permissions_to_user(session)
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        # send request
        test_table_name: str = "test-table"
        test_table_created_on: str = "2023-11-11T03:26:18.557805"
        test_table_user_id: int = 1
        test_table_heritable: bool = False
        test_table_create = {
            "name": test_table_name,
            "description": "",
            "created_on": test_table_created_on,
            "heritable": test_table_heritable,
            "user_id": test_table_user_id,
        }

        # send request
        response = await client.post(
            url="/schema/tables",
            json=test_table_create,
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()

        assert j_resp == {
            "name": "test-table",
            "description": "",
            "created_on": "2023-11-11T03:26:18.557805",
            "user_id": 1,
            "heritable": False,
            "id": 61,
        }

    @pytest.mark.asyncio
    async def test_get_table(self, client: AsyncClient, session: AsyncSession):
        """
        Test get table API
        """
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)

        # send request
        response = await client.get(
            "/schema/tables/1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()

        assert j_resp["name"] == "nzdpu_form"
        assert j_resp["description"] == "NZDPU SCHEMA 4.0"
        assert j_resp["user_id"] == 1
        assert j_resp["heritable"] == False
        assert j_resp["id"] == 1

    @pytest.mark.asyncio
    async def test_update_table(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update table API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)

        test_table_name: str = "test-table"
        test_table_user_id: int = 1
        test_table_create = {
            "name": test_table_name,
            "user_id": test_table_user_id,
        }

        # send request
        response = await client.post(
            url="/schema/tables",
            json=test_table_create,
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        # send request
        response = await client.patch(
            url="/schema/tables/61",
            json={
                "description": "new",
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()

        assert j_resp["name"] == "test-table"
        assert j_resp["description"] == "new"
        assert j_resp["user_id"] == 1
        assert j_resp["heritable"] == False
        assert j_resp["id"] == 61
