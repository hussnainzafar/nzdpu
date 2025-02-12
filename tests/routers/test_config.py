"""Config router tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.db.models import Config, ConfigProperty
from tests.routers.auth_test import AuthTest


class TestConfig(AuthTest):
    """
    Unit tests for config APIs
    """

    async def create_test_config_data(self, session: AsyncSession):
        """
        Method to insert test data for the Config model into test db
        """
        test_data = [
            {
                "name": ConfigProperty.GENERAL_SYSTEM_EMAIL_ADDRESS,
                "type": "String",
                "value": "value_1",
                "description": "Description 1",
            },
            {
                "name": ConfigProperty.DATA_EXPLORER_DOWNLOAD_ALL,
                "type": "Integer",
                "value": "42",
                "description": "Description 2",
            },
        ]

        for data in test_data:
            config = Config(**data)
            session.add(config)

        await session.commit()

    @pytest.mark.asyncio
    async def test_get_config(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test Get Config API
        """

        # Insert test data for the Config model
        await self.create_test_config_data(session)

        # act
        response = await client.get(
            url="/config",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # Assert: Check if the response contains the expected data
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert len(j_resp.get("config", [])) == 2
        assert (
            j_resp.get("config")[0]["name"] == "general_system_email_address"
        )
        assert j_resp.get("config")[1]["type"] == "Integer"
        assert j_resp.get("config")[1]["value"] == 42

    @pytest.mark.asyncio
    async def test_update_config(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test Update Config API
        """

        # Insert test data for the Config model
        await self.create_test_config_data(session)
        # give admin rights to user
        await self.add_admin_permissions_to_user(session)

        # Define the update request data
        update_data = {"general_system_email_address": "value_2"}

        # Send a PATCH request to update the configuration
        response = await client.patch(
            url="/config",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
            json=update_data,
        )

        # Assert: Check if the response indicates a successful update
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()

        assert j_resp.get("success") is True

        # act
        response = await client.get(
            url="/config",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # Assert: Check if the response contains the expected data
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()

        assert j_resp.get("config")[0]["value"] == 42
