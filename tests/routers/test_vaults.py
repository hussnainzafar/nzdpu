"""Unit tests for vaults router"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Vault
from tests.routers.auth_test import AuthTest


class TestVaults(AuthTest):
    """
    Unit tests for vaults APIs
    """

    @pytest.mark.asyncio
    async def test_list_vaults(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List vaults" API
        """
        # create test vaults
        count: int = 5
        vaults: list[Vault] = [
            Vault(
                id=idx,
                name=f"Vault #{idx}",
                storage_type=idx,
                access_type=f"Test Access Type #{idx}",
                access_data=f"Test Access Data #{idx}",
            )
            for idx in range(count)
        ]
        session.add_all(vaults)
        await session.commit()
        # send request
        response = await client.get(
            "/files/vaults",
            params={"id": 1},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert len(j_resp) == count

    @pytest.mark.asyncio
    async def test_get_vault(self, client: AsyncClient, session: AsyncSession):
        """
        Test "Get vault" API
        """
        # create test vault
        vault: Vault = Vault(
            id=1,
            name="Test Vault",
            storage_type=1,
            access_type="Test Access Type",
            access_data="Test Access Data",
        )
        session.add(vault)
        await session.commit()
        vault_id: int = vault.id
        # send request
        response = await client.get(
            f"/files/vaults/{vault_id}",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert j_resp["id"] == 1
