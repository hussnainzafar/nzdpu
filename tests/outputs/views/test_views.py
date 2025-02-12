"""Unit tests for table view outer"""

import json

import pytest
from fastapi.encoders import jsonable_encoder
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app import settings
from app.db.models import TableDef
from app.schemas.table_def import TableDefCreate
from app.schemas.table_view import TableViewCreate
from tests.constants import SCHEMA_FILE_NAME
from tests.routers.auth_test import AuthTest
from tests.routers.utils import create_test_form


class TestViews(AuthTest):
    """
    Unit tests for table view APIs
    """

    async def create_test_table_def(
        self,
        session: AsyncSession,
        name="test_table",
        description="",
        user_id=1,
    ):
        """
        Creates a table view in the DB for testing purposes
        """

        test_schema = TableDefCreate(
            name=name,
            description=description,
            user_id=user_id,
        )
        table_def = TableDef(**test_schema.dict())
        session.add(table_def)
        await session.commit()

    data_dir: str = f"{settings.BASE_DIR}/../tests/data"

    @pytest.mark.asyncio
    async def test_list_views(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list views API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # create test tables
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)

        # send request
        response = await client.get(
            "/schema/views",
            params={"order": "asc"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()

        # load reference schema

        # # USE ME IF NEED TO REBUILD THE RESPONSE
        # with open(
        #     f"{self.data_dir}/list_view_response.json",
        #     "w",
        #     encoding="utf-8",
        # ) as file_resp:
        #     resp = json.dumps(j_resp, indent=4, default=str)
        #     file_resp.write(resp)

        with open(
            f"{self.data_dir}/list_view_response.json", encoding="utf-8"
        ) as f_ref:
            j_ref = json.load(f_ref)

        assert all(
            j_resp[index][key] == j_ref[index][key]
            for index in range(len(j_resp))
            for key in [
                "table_def_id",
                "name",
                "description",
                "revision",
                "revision_id",
                "active",
                "user_id",
                "permissions_set_id",
                "constraint_view",
                "id",
            ]
        )

    @pytest.mark.asyncio
    async def test_create_view(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create view API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        await self.create_test_table_def(
            session,
            name="test_table",
            description="new",
            user_id=1,
        )
        # create test tables
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        # set table view schema
        table_view_name: str = "a"
        table_view_schema = TableViewCreate(
            table_def_id=61,
            name=table_view_name,
            description="",
            revision=1,
            revision_id=None,
            active=True,
            created_on="2023-11-09T10:54:07.869819",
            user_id=1,
            permissions_set_id=None,
            constraint_view={},
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
        assert j_resp["table_def_id"] == 61
        assert j_resp["name"] == "a"
        assert j_resp["description"] == ""
        assert j_resp["active"] == True
        assert j_resp["revision"] == 1
        assert j_resp["created_on"] == "2023-11-09T10:54:07.869819"
        assert j_resp["user_id"] == 1
        assert j_resp["permissions_set_id"] == None
        assert j_resp["constraint_view"] == {}
        assert j_resp["id"] == 61

    @pytest.mark.asyncio
    async def test_get_view(self, client: AsyncClient, session: AsyncSession):
        """
        Test get view API
        """

        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await self.create_test_table_def(
            session,
            name="test_table",
            description="new",
            user_id=1,
        )
        # set table view schema
        table_view_name: str = "a"
        table_view_schema = TableViewCreate(
            table_def_id=61,
            name=table_view_name,
            description="",
            revision=1,
            revision_id=None,
            active=True,
            created_on="2023-11-09T10:54:07.869819",
            user_id=1,
            permissions_set_id=None,
            constraint_view={},
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

        # send request
        response = await client.get(
            "/schema/views/61",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()

        assert j_resp["table_def_id"] == 61
        assert j_resp["name"] == "a"
        assert j_resp["description"] == ""
        assert j_resp["active"] == True
        assert j_resp["revision"] == 1
        assert j_resp["created_on"] == "2023-11-09T10:54:07.869819"
        assert j_resp["user_id"] == 1
        assert j_resp["permissions_set_id"] == None
        assert j_resp["constraint_view"] == {}
        assert j_resp["id"] == 61

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
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await self.create_test_table_def(
            session,
            name="test_table",
            description="new",
            user_id=1,
        )
        # set table view schema
        table_view_name: str = "a"
        table_view_schema = TableViewCreate(
            table_def_id=61,
            name=table_view_name,
            description="",
            revision=1,
            revision_id=None,
            active=True,
            user_id=1,
            permissions_set_id=None,
            constraint_view={},
        )

        # send request
        response = await client.post(
            url="/schema/views",
            json=jsonable_encoder(table_view_schema.model_dump()),
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        # send request
        response = await client.patch(
            url="/schema/views/61",
            json={
                "description": "new1",
                "active": True,
                "permissions_set_id": 0,
                "constraint_view": {},
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert j_resp["table_def_id"] == 61
        assert j_resp["name"] == "a"
        assert j_resp["description"] == "new1"
        assert j_resp["revision"] == 1
        assert j_resp["revision_id"] == None
        assert j_resp["active"] == True
        assert j_resp["user_id"] == 1
        assert j_resp["permissions_set_id"] == 0
        assert j_resp["constraint_view"] == {}
        assert j_resp["id"] == 61

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
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await self.create_test_table_def(
            session,
            name="test_table",
            description="new",
            user_id=1,
        )

        # set table view schema
        table_view_name: str = "a"
        table_view_schema = TableViewCreate(
            table_def_id=61,
            name=table_view_name,
            description="",
            revision=1,
            revision_id=None,
            active=True,
            user_id=1,
            permissions_set_id=None,
            constraint_view={},
        )

        # send request
        response = await client.post(
            url="/schema/views",
            json=jsonable_encoder(table_view_schema.model_dump()),
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # send request
        response = await client.post(
            "/schema/views/revisions",
            params={"name": "a"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert j_resp == {"id": 62, "name": "a", "revision": 2}

    @pytest.mark.asyncio
    async def test_get_view_schema(
        self, client: AsyncClient, session: AsyncSession, redis_client
    ):
        """
        Test "Create View Schema" API when attribute type is not FORM
        """
        await self.add_admin_permissions_to_user(session)

        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await self.create_test_table_def(
            session,
            name="test_table",
            description="new",
            user_id=1,
        )
        # set table view schema
        table_view_name: str = "a"
        table_view_schema = TableViewCreate(
            table_def_id=61,
            name=table_view_name,
            description="new1",
            revision=1,
            revision_id=None,
            active=True,
            user_id=1,
            permissions_set_id=None,
            constraint_view={},
        )

        # send request
        response = await client.post(
            url="/schema/views",
            json=jsonable_encoder(table_view_schema.model_dump()),
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # send request
        response = await client.post(
            "/schema/views/revisions",
            params={"name": "a"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # send request
        response = await client.get(
            f"/schema/views/full/{table_view_name}",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp["table_def_id"] == 61
        assert j_resp["name"] == "a"
        assert j_resp["description"] == "new1"
        assert j_resp["revision"] == 2
        assert j_resp["revision_id"] == None
        assert j_resp["active"] == True
        assert j_resp["user_id"] == 1
        assert j_resp["permissions_set_id"] == None
        assert j_resp["constraint_view"] == {}
        assert j_resp["id"] == 62
        assert isinstance(j_resp["table_def"], dict)
        assert j_resp["table_def"]["name"] == "test_table"
        assert j_resp["table_def"]["description"] == "new"
        assert j_resp["table_def"]["user_id"] == 1
        assert j_resp["table_def"]["id"] == 61
