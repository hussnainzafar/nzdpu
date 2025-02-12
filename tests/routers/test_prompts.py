"""Unit tests for prompts router"""

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AttributePrompt, AuthRole, ColumnDef, TableDef
from app.schemas.column_def import AttributeType
from app.schemas.prompt import AttributePromptCreate
from tests.routers.auth_test import AuthTest

firebase = pytest.mark.skipif("not config.getoption('firebase')")


class TestPrompts(AuthTest):
    """
    Unit tests for choices APIs
    """

    @staticmethod
    async def create_test_prompts(
        labels: list[str], db_session: AsyncSession
    ) -> int:
        """
        Creates a set of prompts for testing

        Parameters
        ----------
        labels - prompt labels

        Returns
        -------
        identifier of the attribute the prompts have been created for
        """

        # create table definition
        table_def = TableDef(name="test_table")
        db_session.add(table_def)
        await db_session.flush()
        table_id: int = table_def.id
        # create attribute
        column_def = ColumnDef(
            table_def_id=table_id,
            name="test_column",
            attribute_type=AttributeType.LABEL,
        )
        db_session.add(column_def)
        await db_session.flush()
        attribute_id: int = column_def.id
        # create test prompts
        prompts: list[AttributePrompt] = []
        for label in labels:
            prompts.append(
                AttributePrompt(column_def_id=attribute_id, value=label)
            )
        db_session.add_all(prompts)
        await db_session.commit()

        return attribute_id

    @pytest.mark.asyncio
    async def test_create_prompt_invalid_column_def_id(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test creating a prompt with an invalid column definition ID.
        This test will ensure that the API correctly handles requests to create prompts with non-existing
        column definition IDs.
        Expected outcome: 404 Not Found status code
        """
        # send request
        prompt_data = {"column_def_id": 9999, "value": "New Prompt"}
        await self.add_role_to_user(session, AuthRole.SCHEMA_EDITOR)
        response = await client.post(
            "/schema/prompts",
            json=prompt_data,
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert (
            response.status_code == status.HTTP_401_UNAUTHORIZED
        ), response.text

    @pytest.mark.asyncio
    async def test_create_prompt_missing_value(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test creating a prompt without a value.
        This test will check if the API correctly rejects requests to create prompts without a value.
        Expected outcome: 422 Unprocessable Entity status code
        """
        # create test prompts and related entities
        attribute_id: int = await self.create_test_prompts(
            ["Prompt #1"], session
        )
        await self.add_role_to_user(session, AuthRole.SCHEMA_EDITOR)

        # send request
        prompt_data = {"column_def_id": attribute_id}
        response = await client.post(
            "/schema/prompts",
            json=prompt_data,
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert (
            response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        ), response.text

    @pytest.mark.asyncio
    async def test_list_prompts(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List prompts" API
        """

        # create test prompts and related entities
        labels = ["Prompt #1", "Prompt #2", "Prompt #3"]
        await self.create_test_prompts(labels, session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # send request
        response = await client.get(
            "/schema/prompts",
            params={"start": 0, "limit": 2},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert j_resp["end"] - j_resp["start"] == 2, "Page size does not match"

        # Check if the returned prompts are in correct page
        ids = [item["id"] for item in j_resp["items"]]
        assert ids[0] == 1, "Pagination does not work correctly"

    @pytest.mark.asyncio
    async def test_list_prompts_no_params(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test to verify that the list of prompts is returned correctly when no parameters are provided.
        The default page size should not exceed 1000.
        """
        # create test prompts and related entities
        labels = ["Prompt #1", "Prompt #2", "Prompt #3"]
        await self.create_test_prompts(labels, session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # send request
        response = await client.get(
            "/schema/prompts",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert (
            j_resp["end"] - j_resp["start"] <= 1000
        ), "Default page size should not exceed 1000"

    @pytest.mark.asyncio
    async def test_list_prompts_invalid_attribute_id(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test to verify that an empty list is returned when an invalid attribute_id is provided.
        """
        # Setup
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # send request
        response = await client.get(
            "/schema/prompts",
            params={"attribute_id": 9999, "start": 0, "limit": 2},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert isinstance(j_resp["items"], list) and not j_resp["items"]

    @pytest.mark.asyncio
    async def test_list_prompts_start_greater_than_total(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test to verify that an empty list is returned when the start parameter is greater than the total
        number of records.
        """
        # create test prompts and related entities
        labels = ["Prompt #1", "Prompt #2", "Prompt #3"]
        await self.create_test_prompts(labels, session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # send request
        response = await client.get(
            "/schema/prompts",
            params={"start": 100, "limit": 2},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert (
            j_resp["end"] - j_resp["start"] == 0
        ), "Size should be 0 when start is greater than total records"

    @pytest.mark.asyncio
    async def test_get_prompt(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Get prompt" API
        """

        # create test prompt and related entities
        labels = ["Prompt #1"]
        attribute_id: int = await self.create_test_prompts(labels, session)
        await self.add_role_to_user(session, AuthRole.SCHEMA_EDITOR)

        # send request
        response = await client.get(
            "/schema/prompts/1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp["column_def_id"] == attribute_id
        assert j_resp["value"] == "Prompt #1"

    @pytest.mark.asyncio
    async def test_get_non_existing_prompt(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        This asynchronous function tests the scenario where a non-existing prompt is requested.
        It sends a GET request to the "/schema/prompts/9999" endpoint with an access token in the headers.
        The expected response status code is 404, indicating that the prompt was not found.
        """
        await self.add_role_to_user(session, AuthRole.SCHEMA_EDITOR)

        response = await client.get(
            "/schema/prompts/9999",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_get_prompt_with_invalid_token(self, client: AsyncClient):
        """
        This asynchronous function tests the scenario where a prompt is requested with an invalid token.
        It sends a GET request to the "/schema/prompts/1" endpoint with an invalid token in the headers.
        The expected response status code is 404, indicating that the prompt was not found due to invalid authorization.
        """

        response = await client.get(
            "/schema/prompts/1",
            headers={
                "accept": "application/json",
                "Authorization": "Bearer invalid_token",
            },
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        j_resp = response.json()
        assert j_resp["detail"] == {
            "global": "Access denied: insufficient permissions."
        }

    @pytest.mark.asyncio
    async def test_create_prompt(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Create prompt" API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create test prompt and related entities
        labels = ["Prompt #1"]
        attribute_id: int = await self.create_test_prompts(labels, session)

        # create schema of new prompt
        prompt_schema = AttributePromptCreate(
            column_def_id=attribute_id, value="Test prompt", role="placeholder"
        )
        # send request
        response = await client.post(
            "/schema/prompts",
            json=prompt_schema.dict(),
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp["column_def_id"] == attribute_id
        assert j_resp["value"] == "Test prompt"
        assert j_resp["role"] == "placeholder"

    @pytest.mark.asyncio
    async def test_update_prompt(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Update choice" API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create test prompt and related entities
        labels = ["Prompt #1"]
        attribute_id: int = await self.create_test_prompts(labels, session)

        # send request
        response = await client.patch(
            "/schema/prompts/1",
            json={"value": "Prompt #1 - Rev 2", "role": "info"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp["column_def_id"] == attribute_id
        assert j_resp["value"] == "Prompt #1 - Rev 2"
        assert j_resp["role"] == "info"

    @pytest.mark.asyncio
    async def test_update_non_existing_prompt(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test updating a non-existing prompt.
        This test will ensure that the API correctly handles requests to update prompts that do not exist.
        Expected outcome: 404 Not Found status code
        """
        await self.add_role_to_user(session, AuthRole.SCHEMA_EDITOR)

        response = await client.patch(
            "/schema/prompts/9999",
            json={"value": "Prompt #1 - Rev 2", "role": "info"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_update_prompt_without_token(self, client: AsyncClient):
        """
        Test updating a prompt without an authorization token.
        This test will check if the API correctly rejects requests without an authorization token.
        Expected outcome: 401 Unauthorized status code
        """
        response = await client.patch(
            "/schema/prompts/1",
            json={"value": "Prompt #1 - Rev 2", "role": "info"},
            headers={"accept": "application/json"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_update_prompt_with_invalid_token(self, client: AsyncClient):
        """
        Test updating a prompt with an invalid authorization token.
        This test will check if the API correctly rejects requests with an invalid authorization token.
        Expected outcome: 401 Unauthorized status code
        """
        response = await client.patch(
            "/schema/prompts/1",
            json={"value": "Prompt #1 - Rev 2", "role": "info"},
            headers={
                "accept": "application/json",
                "Authorization": "Bearer invalid_token",
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        j_resp = response.json()
        assert j_resp["detail"] == {
            "global": "Access denied: insufficient permissions."
        }

    @pytest.mark.asyncio
    async def test_update_prompt_with_invalid_data(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test updating a prompt with invalid data.
        This test will check if the API correctly rejects requests with invalid data.
        Expected outcome: 422
        """

        # arrange
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # create test prompt and related entities
        labels = ["Prompt #1"]
        await self.create_test_prompts(labels, session)

        # act
        response = await client.patch(
            "/schema/prompts/1",
            json={"invalid_key": "invalid_value"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_list_prompts_with_multilanguage_content(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list prompts API with multilanguage content
        """
        # add admin permission to user
        table_def = TableDef(name="test_table")
        session.add(table_def)
        await session.flush()
        table_id: int = table_def.id
        # create attribute
        column_def = ColumnDef(
            table_def_id=table_id,
            name="test_column",
            attribute_type=AttributeType.LABEL,
        )
        session.add(column_def)
        await session.flush()
        await self.add_admin_permissions_to_user(session)

        # define test data with multilanguage content
        test_data = [
            {"language_code": "en-US", "value": "test_prompt"},
            {"language_code": "zh-CN", "value": "测试提示"},
            {"language_code": "fr-FR", "value": "suggestion_de_test"},
            {"language_code": "de-DE", "value": "testhinweis"},
            {"language_code": "es-ES", "value": "sugerencia_de_prueba"},
            {"language_code": "ru-RU", "value": "подсказка_теста"},
            {"language_code": "ja-JP", "value": "テストプロンプト"},
            {"language_code": "ar-SA", "value": "اقتراح_الاختبار"},
            {"language_code": "el-GR", "value": "πρόταση_δοκιμής"},
        ]

        # create prompts in database
        for data in test_data:
            prompt_schema = AttributePromptCreate(
                column_def_id=1,
                value=data["value"],
                language_code=data["language_code"],
            )
            response = await client.post(
                "/schema/prompts",
                json=prompt_schema.dict(),
                headers={
                    "accept": "application/json",
                    "Authorization": f"Bearer {self.access_token}",
                },
            )
            assert response.status_code == status.HTTP_200_OK, response.text

        # send request
        response = await client.get(
            "/schema/prompts",
            params={"attribute_id": 1},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        j_resp["items"] = j_resp["items"][::-1]
        assert "id" in j_resp["items"][0] and j_resp["items"][0]["id"] == 1
        assert (
            "language_code" in j_resp["items"][0]
            and j_resp["items"][0]["language_code"] == "en-US"
        )
        assert (
            "value" in j_resp["items"][0]
            and j_resp["items"][0]["value"] == "test_prompt"
        )
        assert "id" in j_resp["items"][1] and j_resp["items"][1]["id"] == 2
        assert (
            "language_code" in j_resp["items"][1]
            and j_resp["items"][1]["language_code"] == "zh-CN"
        )

        assert (
            "value" in j_resp["items"][1]
            and j_resp["items"][1]["value"] == "测试提示"
        )
        assert "id" in j_resp["items"][2] and j_resp["items"][2]["id"] == 3
        assert (
            "language_code" in j_resp["items"][2]
            and j_resp["items"][2]["language_code"] == "fr-FR"
        )
        assert (
            "value" in j_resp["items"][2]
            and j_resp["items"][2]["value"] == "suggestion_de_test"
        )
        assert "id" in j_resp["items"][3] and j_resp["items"][3]["id"] == 4
        assert (
            "language_code" in j_resp["items"][3]
            and j_resp["items"][3]["language_code"] == "de-DE"
        )
        assert (
            "value" in j_resp["items"][3]
            and j_resp["items"][3]["value"] == "testhinweis"
        )
        assert "id" in j_resp["items"][4] and j_resp["items"][4]["id"] == 5
        assert (
            "language_code" in j_resp["items"][4]
            and j_resp["items"][4]["language_code"] == "es-ES"
        )
        assert (
            "value" in j_resp["items"][4]
            and j_resp["items"][4]["value"] == "sugerencia_de_prueba"
        )
        assert "id" in j_resp["items"][5] and j_resp["items"][5]["id"] == 6
        assert (
            "language_code" in j_resp["items"][5]
            and j_resp["items"][5]["language_code"] == "ru-RU"
        )
        assert (
            "value" in j_resp["items"][5]
            and j_resp["items"][5]["value"] == "подсказка_теста"
        )
        assert "id" in j_resp["items"][6] and j_resp["items"][6]["id"] == 7
        assert (
            "language_code" in j_resp["items"][6]
            and j_resp["items"][6]["language_code"] == "ja-JP"
        )
        assert (
            "value" in j_resp["items"][6]
            and j_resp["items"][6]["value"] == "テストプロンプト"
        )
        assert "id" in j_resp["items"][7] and j_resp["items"][7]["id"] == 8
        assert (
            "language_code" in j_resp["items"][7]
            and j_resp["items"][7]["language_code"] == "ar-SA"
        )
        assert (
            "value" in j_resp["items"][7]
            and j_resp["items"][7]["value"] == "اقتراح_الاختبار"
        )
        assert "id" in j_resp["items"][8] and j_resp["items"][8]["id"] == 9
        assert (
            "language_code" in j_resp["items"][8]
            and j_resp["items"][8]["language_code"] == "el-GR"
        )
        assert (
            "value" in j_resp["items"][8]
            and j_resp["items"][8]["value"] == "πρόταση_δοκιμής"
        )
