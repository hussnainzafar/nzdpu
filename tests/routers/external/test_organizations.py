"""Unit tests for organizations"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.db.models import Organization
from app.service.core.cache import CoreMemoryCache
from tests.routers.auth_test import AuthTest


class TestOrganizations(AuthTest):
    """
    Unit tests for organizations APIs
    """

    @pytest.mark.asyncio
    async def test_get_organization(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
    ):
        """
        Test "Get organization" API
        """
        # create test organization
        org = Organization(
            lei="001GPB6A9XPE8XJICC14", legal_name="Test Org", nz_id=1001
        )
        session.add(org)
        await session.commit()
        await static_cache.refresh_values()

        # send request
        response = await client.get(
            "/external/by-lei",
            params={"lei": "001GPB6A9XPE8XJICC14"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK

        j_resp = response.json()
        assert j_resp["lei"] == "001GPB6A9XPE8XJICC14"
        assert j_resp["legal_name"] == "Test Org"

    @pytest.mark.asyncio
    async def test_get_organization_not_found(self, client: AsyncClient):
        """
        Test "Get organization" API with non-existing LEI
        """
        # send request
        response = await client.get(
            "/external/nonexistingLEI",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_update_organization(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
    ):
        """
        Test "Update organization" API
        """
        # create test organization
        org = Organization(
            lei="001GPB6A9XPE8XJICC14", legal_name="Test Org", nz_id=1001
        )
        session.add(org)
        await session.commit()
        await static_cache.refresh_values()

        # send request
        response = await client.patch(
            "/external/by-lei",
            params={"lei": "001GPB6A9XPE8XJICC14"},
            json={
                "company_type": "example",
                "company_website": "www.example.com",
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK

        j_resp = response.json()
        assert j_resp["lei"] == "001GPB6A9XPE8XJICC14"
        assert j_resp["legal_name"] == "Test Org"
        assert j_resp["company_type"] == "example"
        assert j_resp["company_website"] == "www.example.com"

    @pytest.mark.asyncio
    async def test_update_organization_not_found(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Update organization not found by lei" API
        """
        # create test organization
        org = Organization(
            lei="001GPB6A9XPE8XJICC14", legal_name="Test Org", nz_id=1001
        )
        session.add(org)
        await session.commit()

        # send request
        response = await client.patch(
            "/external/by-lei",
            params={"lei": "254900V0UJEX6JQ3ZS32"},
            json={
                "company_type": "example",
                "company_website": "www.example.com",
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        j_resp = response.json()
        assert j_resp["detail"]["lei"] == (
            "No organization matches the given LEI."
        )

    @pytest.mark.asyncio
    async def test_update_organization_company_website(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
    ):
        """
        Test "Update organization company website" API
        """
        # create test organization
        org = Organization(
            lei="001GPB6A9XPE8XJICC14", legal_name="Test Org", nz_id=1001
        )
        session.add(org)
        await session.commit()
        await static_cache.refresh_values()

        # send request
        response = await client.patch(
            "/external/by-lei",
            params={"lei": "001GPB6A9XPE8XJICC14"},
            json={"company_website": "www.example.com"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        # print(j_resp)
        assert j_resp["lei"] == "001GPB6A9XPE8XJICC14"
        assert j_resp["legal_name"] == "Test Org"
        assert j_resp["company_type"] is None
        assert j_resp["company_website"] == "www.example.com"

    @pytest.mark.asyncio
    async def test_update_organization_company_type(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Update organization company type" API
        """
        # create test organization
        org = Organization(
            lei="001GPB6A9XPE8XJICC14", legal_name="Test Org", nz_id=1001
        )
        session.add(org)
        await session.commit()

        # send request
        response = await client.patch(
            "/external/by-lei",
            params={"lei": "001GPB6A9XPE8XJICC14"},
            json={"company_type": "example"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        # print(j_resp)
        assert j_resp["lei"] == "001GPB6A9XPE8XJICC14"
        assert j_resp["legal_name"] == "Test Org"
        assert j_resp["company_type"] == "example"
        assert j_resp["company_website"] is None
