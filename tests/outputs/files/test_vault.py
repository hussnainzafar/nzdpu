import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Vault
from tests.routers.auth_test import AuthTest


class TestPermissionOutputGet(AuthTest):
    @pytest.mark.asyncio
    async def test_get_vault_output(
        self, client: AsyncClient, session: AsyncSession
    ):
        vaults: list[Vault] = [
            Vault(
                id=1,
                name="Google Cloud Storage",
                storage_type=0,
                access_type="google_adc",
                access_data="",
            )
        ]
        session.add_all(vaults)
        await session.commit()

        response = await client.get(
            url="/files/vaults/1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == 200

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp == {
            "id": 1,
            "name": "Google Cloud Storage",
            "storage_type": 0,
            "access_type": "google_adc",
            "access_data": "",
        }

    @pytest.mark.asyncio
    async def test_list_vault_output(
        self, client: AsyncClient, session: AsyncSession
    ):
        vaults: list[Vault] = [
            Vault(
                id=1,
                name="Google Cloud Storage",
                storage_type=0,
                access_type="google_adc",
                access_data="",
            ),
        ]
        session.add_all(vaults)
        await session.commit()

        response = await client.get(
            url="/files/vaults",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp[0] == {
            "id": 1,
            "name": "Google Cloud Storage",
            "storage_type": 0,
            "access_type": "google_adc",
            "access_data": "",
        }
