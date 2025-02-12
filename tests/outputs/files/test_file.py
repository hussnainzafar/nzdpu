import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.util import md5_hex

from app.db.models import FileRegistry, Vault
from tests.routers.auth_test import AuthTest


@pytest.fixture
def vault():
    return Vault(
        id=0,
        name="Test Vault",
        storage_type=0,
        access_type="public",
        access_data="",
    )


class TestPermissionOutputGet(AuthTest):
    @pytest.mark.asyncio
    async def test_get_file_output(
        self, client: AsyncClient, session: AsyncSession, vault
    ):
        session.add(vault)
        await session.commit()

        files: list[FileRegistry] = [
            FileRegistry(
                value_id=0,
                vault_id=vault.id,
                vault_obj_id="",
                view_id=0,
                file_size=0,
                vault_path="",
                checksum="",
                md5=md5_hex("hex"),
            )
        ]
        session.add_all(files)
        await session.commit()

        response = await client.get(
            url="/files",
            params={"view_id": 0},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == 200
        assert response.status_code == status.HTTP_200_OK, response.text

    @pytest.mark.asyncio
    async def test_list_file_output(
        self, client: AsyncClient, session: AsyncSession, vault
    ):
        session.add(vault)
        await session.commit()

        files: list[FileRegistry] = [
            FileRegistry(
                id=1,
                value_id=0,
                vault_id=vault.id,
                vault_obj_id="",
                view_id=0,
                file_size=0,
                vault_path="",
                checksum="",
                md5=md5_hex("hex"),
            ),
        ]
        session.add_all(files)
        await session.commit()

        response = await client.get(
            url="/files",
            params={"view_id": 0},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == 200
        assert response.status_code == status.HTTP_200_OK, response.text


class TestPermissionOutputPost(AuthTest):
    @pytest.mark.asyncio
    async def test_create_file_output(
        self, client: AsyncClient, session: AsyncSession
    ):
        # act
        response = await client.post(
            url="/files",
            json={
                "id": 0,
                "value_id": 0,
                "vault_id": 0,
                "vault_obj_id": "",
                "view_id": 0,
                "created_on": None,
                "file_size": 0,
                "vault_path": "",
                "checksum": "",
                "md5": "0",
                "base64": "",
            },
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 403
