"""Unit tests for managed_files router"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuthRole, FileRegistry
from tests.routers.auth_test import AuthTest


class TestManagedFile(AuthTest):
    """
    Unit tests for file APIs
    """

    @pytest.mark.asyncio
    async def test_list_files(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List Files" API
        """
        # create test files
        count: int = 0
        view_id = 1  # Replace with the desired view ID
        files: list[FileRegistry] = [
            FileRegistry(vault_id=idx, view_id=view_id, vault_path="")
            for idx in range(count)
        ]
        session.add_all(files)
        await session.commit()
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # send request
        response = await client.get(
            "/files",
            params={"view_id": view_id},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200
        j_resp = response.json()
        assert len(j_resp) == count
