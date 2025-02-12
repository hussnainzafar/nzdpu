"""Unit tests for choices output"""

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings
from app.schemas.choice import ChoiceCreate, ChoiceCreateSet
from tests.constants import SCHEMA_FILE_NAME
from tests.routers.auth_test import AuthTest
from tests.routers.utils import create_test_form


class TestChoices(AuthTest):
    """
    Unit tests for choices APIs
    """

    data_dir: str = f"{settings.BASE_DIR}/../tests/data"

    # List Choices
    @pytest.mark.asyncio
    async def test_list_choices(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List choices" API
        """
        # create test choices
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        # Test without set_id parameter
        response = await client.get(
            "/schema/choices",
            params={"start": 0, "limit": 1},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp == {
            "start": 0,
            "end": 0,
            "total": 0,
            "items": [],
        }

    # Create Choice
    @pytest.mark.asyncio
    async def test_create_choice(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Create choice" API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # set choice schema
        choice_schema = ChoiceCreate(
            choice_id=0,
            set_id=0,
            set_name="new_choice_id",
            value="new_choice_id",
            description="",
            order=1,
            language_code="en_US",
        )
        # send request
        response = await client.post(
            "/schema/choices",
            json=choice_schema.dict(),
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp == {
            "choice_id": 1000000,
            "set_id": 1,
            "set_name": "new_choice_id",
            "value": "new_choice_id",
            "description": "",
            "order": 1,
            "language_code": "en_US",
            "id": 1,
        }

    @pytest.mark.asyncio
    async def test_create_choice_sets(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "create choice sets" API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create input schema and populate database with some choice sets
        schema = ChoiceCreateSet(
            set_name="new_choice_set",
            labels=["new_label_name"],
            language_code="en_US",
        )
        response = await client.post(
            "/schema/choices/set",
            json=schema.dict(),
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp == {"set_id": 1}

    @pytest.mark.asyncio
    async def test_list_choice_set_with_multiple_choices(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List choice sets" API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)

        # send request to list choice sets
        response = await client.get(
            "schema/choices/sets?limit=1&start=0",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        # We do not have choices in schema v4 so we test for 0
        assert j_resp == {
            "start": 0,
            "end": 0,
            "total": 0,
            "items": [],
        }

    # Comment this for now since we do not have any choice list in the schema v4
    # @pytest.mark.asyncio
    # async def test_get_choice_set_by_name(
    #     self, client: AsyncClient, session: AsyncSession
    # ):
    #     """
    #     Test case for when the choice set exists in the database.
    #     getting choice set by name

    #     """
    #     await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
    #     set_name: str = "source_list"
    #     # send request
    #     response = await client.get(
    #         f"schema/choices/sets/by-name?name={set_name}",
    #         headers={
    #             "accept": "application/json",
    #             "Authorization": f"Bearer {self.access_token}",
    #         },
    #     )

    #     assert response.status_code == status.HTTP_200_OK, response.text
    #     j_resp = response.json()
    #     assert j_resp == {
    #         "set_id": 1,
    #         "set_name": "source_list",
    #         "language_code": "en_US",
    #         "labels": [
    #             "CDP Climate Change 2015",
    #             "CDP Climate Change 2016",
    #             "CDP Climate Change 2017",
    #             "CDP Climate Change 2018",
    #             "CDP Climate Change 2019",
    #             "CDP Climate Change 2020",
    #             "CDP Climate Change 2021",
    #             "CDP Climate Change 2022",
    #         ],
    #     }

    # @pytest.mark.asyncio
    # async def test_get_choice_by_id(
    #     self, client: AsyncClient, session: AsyncSession
    # ):
    #     """
    #     get choice by id
    #     """
    #     await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
    #     record_id: int = 2
    #     await self.add_role_to_user(session, AuthRole.SCHEMA_EDITOR)

    #     # send request
    #     response = await client.get(
    #         f"/schema/choices/{record_id}",
    #         headers={
    #             "accept": "application/json",
    #             "Authorization": f"Bearer {self.access_token}",
    #         },
    #     )

    #     assert response.status_code == status.HTTP_200_OK, response.text
    #     j_resp = response.json()
    #     assert j_resp == {
    #         "choice_id": 760003,
    #         "set_id": 1,
    #         "set_name": "source_list",
    #         "value": "CDP Climate Change 2016",
    #         "description": "",
    #         "order": 2,
    #         "language_code": "en_US",
    #         "id": 2,
    #     }

    # @pytest.mark.asyncio
    # async def test_update_choice(
    #     self, client: AsyncClient, session: AsyncSession
    # ):
    #     """
    #     Test "Update choice" API
    #     """
    #     # add admin permission to user
    #     await self.add_admin_permissions_to_user(session)

    #     # create test choice
    #     await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
    #     choice_id: int = 1
    #     # send request
    #     response = await client.patch(
    #         f"/schema/choices/{choice_id}",
    #         json={
    #             "value": "Test Case - new",
    #             "description": "test",
    #             "order": 1,
    #         },
    #         headers={
    #             "accept": "application/json",
    #             "Authorization": f"Bearer {self.access_token}",
    #         },
    #     )

    #     assert response.status_code == status.HTTP_200_OK, response.text
    #     j_resp = response.json()
    #     assert j_resp == {
    #         "choice_id": 760002,
    #         "set_id": 1,
    #         "set_name": "source_list",
    #         "value": "Test Case - new",
    #         "description": "test",
    #         "order": 1,
    #         "language_code": "en_US",
    #         "id": 1,
    #     }
