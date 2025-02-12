"""Unit tests for tables router"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app import settings
from app.db.models import AuthRole, TableDef
from app.routers.utils import ErrorMessage
from app.schemas.table_def import TableDefCreate
from tests.routers.auth_test import AuthTest

from .utils import create_test_form, create_test_table_def

firebase = pytest.mark.skipif("not config.getoption('firebase')")


class TestTables(AuthTest):
    """
    Unit tests for tables APIs
    """

    data_dir: str = f"{settings.BASE_DIR}/../tests/data"

    @pytest.mark.asyncio
    async def test_list_tables(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List tables" API
        """
        # create test tables
        count: int = 5
        tables: list[TableDefCreate] = [
            TableDefCreate(
                name=f"sample_questionnaire #{idx}",
                description=f"A sample questionnaire #{idx}",
                user_id=1,
            )
            for idx in range(5)
        ]

        for table_def_create in tables:
            table_def = TableDef(**table_def_create.dict())
            session.add(table_def)
            await session.commit()

        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # send request
        response = await client.get(
            "/schema/tables",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert len(j_resp) == count
        assert "id" in j_resp[0] and j_resp[0]["id"] == 1
        assert (
            "name" in j_resp[0]
            and j_resp[0]["name"] == "sample_questionnaire #0"
        )

    @pytest.mark.asyncio
    async def test_list_tables_empty(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List tables" API when there are no tables
        """
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # send request
        response = await client.get(
            "/schema/tables",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert len(j_resp) == 0

    @pytest.mark.asyncio
    async def test_list_tables_unauthorized(self, client: AsyncClient):
        """
        Test "List tables" API for unauthorized access
        """
        # send request without authorization header
        response = await client.get(
            "/schema/tables", headers={"accept": "application/json"}
        )

        assert response.status_code == 401, response.text

    @pytest.mark.asyncio
    async def test_list_tables_incorrect_count(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List tables" API for incorrect table count
        """
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # create test tables
        count: int = 5
        tables: list[TableDefCreate] = [
            TableDefCreate(
                name=f"sample_questionnaire #{idx}",
                description=f"A sample questionnaire #{idx}",
                user_id=1,
            )
            for idx in range(count)
        ]

        for table_def_create in tables:
            table_def = TableDef(**table_def_create.dict())
            session.add(table_def)
            await session.commit()

        # send request
        response = await client.get(
            "/schema/tables",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert len(j_resp) != count - 1

    @pytest.mark.asyncio
    async def test_get_table(self, client: AsyncClient, session: AsyncSession):
        """
        Test get table API
        """
        # create test table
        await create_test_table_def(session)

        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # send request
        response = await client.get(
            "/schema/tables/1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1
        assert "name" in j_resp and j_resp["name"] == "nzdpu_form"

    @pytest.mark.asyncio
    async def test_get_non_existent_table(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test get non-existent table API
        """
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # send request to get table
        response = await client.get(
            url="/schema/tables/9999",  # assuming 9999 is an id that does not exist
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 404, response.text

    @pytest.mark.asyncio
    async def test_get_table_without_authorization(self, client: AsyncClient):
        """
        Test get table API without authorization
        """
        # send request without authorization header
        response = await client.get(
            url="/schema/tables/1",
            headers={
                "accept": "application/json",
            },
        )

        assert (
            response.status_code == 401
        ), response.text  # expecting unauthorized status code

    @pytest.mark.asyncio
    async def test_get_table_with_invalid_id_format(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test get table API with invalid table ID format
        """
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # send request with invalid table ID format
        response = await client.get(
            url="/schema/tables/abc",  # 'abc' is not a valid integer ID
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert (
            response.status_code == 422
        ), response.text  # expecting bad request status code

    @pytest.mark.asyncio
    async def test_create_table(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create table API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create test table def
        test_table_name: str = "sample_questionnaire"
        test_table_description: str = "sample_description"
        test_table_create = {
            "name": test_table_name,
            "description": test_table_description,
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

        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1
        assert (
            "description" in j_resp
            and j_resp["description"] == test_table_description
        )
        assert "name" in j_resp and j_resp["name"] == test_table_name

    @pytest.mark.asyncio
    async def test_create_table_exists(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create table API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create test table def
        test_table_name: str = "sample_questionnaire"
        test_table_description: str = "sample_description"
        test_table_create = {
            "name": test_table_name,
            "description": test_table_description,
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

        assert response.status_code == status.HTTP_200_OK

        # attempt to create same table again
        response = await client.post(
            url="/schema/tables",
            json=test_table_create,
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        j_resp = response.json()
        assert j_resp["detail"]["table"] == ErrorMessage.TABLE_DEF_EXISTS

    @pytest.mark.asyncio
    async def test_create_table_invalid_name(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create table API with invalid table name
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create test table def with invalid name
        test_table_description: str = "sample_description"
        test_table_create = {
            "description": test_table_description,
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

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_create_table_missing_auth(
        self, client: AsyncClient, session: AsyncSession
    ):
        """_summary_

        Args:
            client (AsyncClient): _description_
            session (AsyncSession): _description_
        """
        # create test table def
        test_table_name: str = "sample_questionnaire"
        test_table_description: str = "sample_description"
        test_table_create = {
            "name": test_table_name,
            "description": test_table_description,
        }

        # send request without authorization header
        response = await client.post(
            url="/schema/tables",
            json=test_table_create,
            headers={
                "accept": "application/json",
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_create_table_non_admin(
        self, client: AsyncClient, session: AsyncSession
    ):
        """_summary_

        Args:
            client (AsyncClient): _description_
            session (AsyncSession): _description_
        """
        # create test table def
        test_table_name: str = "sample_questionnaire"
        test_table_description: str = "sample_description"
        test_table_create = {
            "name": test_table_name,
            "description": test_table_description,
        }

        # send request with non-admin user's access token
        response = await client.post(
            url="/schema/tables",
            json=test_table_create,
            headers={
                "accept": "application/json",
                "authorization": "Bearer test_non_admin_access_token",
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        j_resp = response.json()
        assert j_resp["detail"] == {
            "global": "Access denied: insufficient permissions."
        }

    @pytest.mark.asyncio
    async def test_update_table(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update table API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create test table
        await create_test_table_def(session)

        # send request
        response = await client.patch(
            url="/schema/tables/1",
            json={
                "description": "New table description",
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1
        # here we check successful update of record
        assert j_resp["description"] == "New table description"

    @pytest.mark.asyncio
    async def test_update_nonexistent_table(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update API for nonexistent table
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # send request
        response = await client.patch(
            url="/schema/tables/999",  # non-existent table id
            json={
                "description": "New table description",
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert (
            response.status_code == 404
        ), response.text  # expecting 'Not Found' status code

    @pytest.mark.asyncio
    async def test_unauthorized_update_table(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update API for unauthorized user
        """
        # create test table
        await create_test_table_def(session)

        # send request
        response = await client.patch(
            url="/schema/tables/1",
            json={
                "description": "New table description",
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",  # token of a user without admin permissions
            },
        )

        assert (
            response.status_code == 403
        ), response.text  # expecting 'Forbidden' status code

    @pytest.mark.asyncio
    async def test_apply_filtering_by_name(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List Tables with filtering by name" API
        """

        # create test forms
        await create_test_form(f"{self.data_dir}/form-create.json", session)
        await create_test_form(f"{self.data_dir}/nzdpu-scope-1.json", session)

        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # send request
        response = await client.get(
            '/schema/tables?filter_by={"name":"scope"}',
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert len(j_resp) == 4
        assert "scope" in j_resp[0]["name"]
        assert "scope" in j_resp[1]["name"]
        assert "scope" in j_resp[2]["name"]
        assert "scope" in j_resp[3]["name"]

    @pytest.mark.asyncio
    async def test_apply_order_by_id(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List Tables with order by id" API
        """

        # create test forms
        await create_test_form(f"{self.data_dir}/form-create.json", session)
        await create_test_form(f"{self.data_dir}/nzdpu-scope-1.json", session)

        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # send request
        response = await client.get(
            '/schema/tables?order_by=["id","name"]',
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
    async def test_apply_order_by_name(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List Tables with order by name" API
        """

        # create test forms
        await create_test_form(f"{self.data_dir}/form-create.json", session)
        await create_test_form(f"{self.data_dir}/nzdpu-scope-1.json", session)

        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # send request
        response = await client.get(
            '/schema/tables?order_by=["name"]',
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert len(j_resp) == 5
        assert j_resp[0]["name"] == "nzdpu_form"
        assert j_resp[1]["name"] == "nzdpu_scope_1"
        assert j_resp[2]["name"] == "scope_1_exclusion_form"

    @pytest.mark.asyncio
    async def test_apply_order_by_id_order_desc(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List Tables with order by id order desc" API
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
        # print(j_resp)
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
        # print(j_resp)
        assert (
            j_resp["detail"] == "Invalid order_by value example."
            " Must be id, name, active or created_on."
        )
