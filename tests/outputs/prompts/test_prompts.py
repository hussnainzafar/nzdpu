"""Unit tests for prompts output"""

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings
from app.db.models import AuthRole
from app.schemas.prompt import AttributePromptCreate
from tests.constants import SCHEMA_FILE_NAME
from tests.routers.auth_test import AuthTest
from tests.routers.utils import create_test_form


class TestPrompts(AuthTest):
    """
    Unit tests for Prompts output
    """

    data_dir: str = f"{settings.BASE_DIR}/../tests/data"

    @pytest.mark.asyncio
    async def test_list_prompts(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List prompts" API
        """
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # send request
        response = await client.get(
            "/schema/prompts",
            params={"start": 0, "limit": 3},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp == {
            "start": 0,
            "end": 3,
            "total": 1256,
            "items": [
                {
                    "column_def_id": 1,
                    "value": "Organization Identifier",
                    "description": "",
                    "language_code": "en_US",
                    "role": "label",
                    "id": 1,
                },
                {
                    "column_def_id": 2,
                    "value": "Legal Entity Identifier (LEI)",
                    "description": "",
                    "language_code": "en_US",
                    "role": "label",
                    "id": 2,
                },
                {
                    "column_def_id": 3,
                    "value": "Disclosure source",
                    "description": "",
                    "language_code": "en_US",
                    "role": "label",
                    "id": 3,
                },
            ],
        }

    @pytest.mark.asyncio
    async def test_create_prompt(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Create prompt" API
        """
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # create schema of new prompt
        prompt_schema = AttributePromptCreate(
            column_def_id=2,
            value="Reporting date - test",
            description="",
            language_code="en_US",
            role="label",
        )
        # send request
        response = await client.post(
            "/schema/prompts",
            json=prompt_schema.model_dump(),
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp == {
            "column_def_id": 2,
            "value": "Reporting date - test",
            "description": "",
            "language_code": "en_US",
            "role": "label",
            "id": 1257,
        }

    @pytest.mark.asyncio
    async def test_get_prompts(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "get prompts" API
        """
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await self.add_role_to_user(session, AuthRole.SCHEMA_EDITOR)
        # get the promt agaist specific id
        response = await client.get(
            "/schema/prompts/1009",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp == {
            "column_def_id": 1009,
            "value": "Percentage of base year total Scope 3 Category 10 (Processing of sold products) GHG emissions covered by target",
            "description": "",
            "language_code": "en_US",
            "role": "label",
            "id": 1009,
        }

    @pytest.mark.asyncio
    async def test_update_prompt(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Create prompt" API
        """
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # create schema of new prompt
        prompt_schema = AttributePromptCreate(
            column_def_id=2,
            value="Reporting date - test",
            description="",
            language_code="en_US",
            role="label",
        )
        # send request
        response = await client.post(
            "/schema/prompts",
            json=prompt_schema.model_dump(),
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp == {
            "column_def_id": 2,
            "value": "Reporting date - test",
            "description": "",
            "language_code": "en_US",
            "role": "label",
            "id": 1257,
        }

        # send request
        response = await client.patch(
            "/schema/prompts/1009",
            json={"value": "Test2", "description": "", "role": "label"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp == {
            "column_def_id": 1009,
            "value": "Test2",
            "description": "",
            "language_code": "en_US",
            "role": "label",
            "id": 1009,
        }
