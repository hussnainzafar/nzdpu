"""Unit tests for organizations"""

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.db.models import Organization
from app.service.core.cache import CoreMemoryCache
from tests.routers.auth_test import AuthTest


class TestOrganizations(AuthTest):
    """
    Unit tests for  Output/organizations
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
            nz_id=1002,
            lei="549300T6IPOCDWLKC615",
            legal_name="Hitachi,Ltd.",
            jurisdiction="Japan",
            company_type="Corporation",
            company_website=None,
            headquarter_address_lines="丸の内一丁目6番6号",
            headquarter_address_number=None,
            headquarter_city="東京都 千代田区",
            headquarter_country="JP",
            headquarter_language="ja",
            headquarter_postal_code="100-8280",
            headquarter_region=None,
            legal_address_lines="丸の内一丁目6番6号",
            legal_address_number=None,
            legal_city="東京都 千代田区",
            legal_country="JP",
            legal_language="ja",
            legal_postal_code="100-8280",
            legal_region=None,
            sics_sector="Resource Transformation",
            sics_sub_sector="Industrials",
            sics_industry="Electrical & Electronic Equipment",
            created_on=datetime.fromisoformat("2023-10-24T09:47:12.926507"),
            last_updated_on=datetime.fromisoformat(
                "2023-10-24T09:47:12.926507"
            ),
            active=True,
        )
        session.add(org)
        await session.commit()
        await static_cache.refresh_values()

        # send request
        response = await client.get(
            "/external/by-lei",
            params={"lei": "549300T6IPOCDWLKC615"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert j_resp == {
            "sing_id": None,
            "nz_id": 1002,
            "lei": "549300T6IPOCDWLKC615",
            "legal_name": "Hitachi,Ltd.",
            "isics": None,
            "jurisdiction": "Japan",
            "company_type": "Corporation",
            "company_website": None,
            "headquarter_address_lines": "丸の内一丁目6番6号",
            "headquarter_address_number": None,
            "headquarter_city": "東京都 千代田区",
            "headquarter_country": "JP",
            "headquarter_language": "ja",
            "headquarter_postal_code": "100-8280",
            "headquarter_region": None,
            "legal_address_lines": "丸の内一丁目6番6号",
            "legal_address_number": None,
            "legal_city": "東京都 千代田区",
            "legal_country": "JP",
            "legal_language": "ja",
            "legal_postal_code": "100-8280",
            "legal_region": None,
            "sics_sector": "Resource Transformation",
            "sics_sub_sector": "Industrials",
            "sics_industry": "Electrical & Electronic Equipment",
            "duns": None,
            "gleif": None,
            "created_on": "2023-10-24T09:47:12.926507",
            "last_updated_on": "2023-10-24T09:47:12.926507",
            "active": True,
        }

    @pytest.mark.asyncio
    async def test_update_organization(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Update organization" API
        """
        # create test organization
        org = Organization(
            nz_id=1002,
            lei="549300T6IPOCDWLKC615",
            legal_name="Hitachi,Ltd.",
            jurisdiction="Japan",
            company_type="string",
            company_website="string",
            headquarter_address_lines="丸の内一丁目6番6号",
            headquarter_address_number=None,
            headquarter_city="東京都 千代田区",
            headquarter_country="JP",
            headquarter_language="ja",
            headquarter_postal_code="100-8280",
            headquarter_region=None,
            legal_address_lines="丸の内一丁目6番6号",
            legal_address_number=None,
            legal_city="東京都 千代田区",
            legal_country="JP",
            legal_language="ja",
            legal_postal_code="100-8280",
            legal_region=None,
            sics_sector="Resource Transformation",
            sics_sub_sector="Industrials",
            sics_industry="Electrical & Electronic Equipment",
            created_on=datetime.fromisoformat("2023-10-24T09:47:12.926507"),
            last_updated_on=datetime.fromisoformat(
                "2023-10-24T09:47:12.926507"
            ),
            active=True,
        )
        session.add(org)
        await session.commit()

        # send request
        response = await client.patch(
            "/external/by-lei",
            params={"lei": "549300T6IPOCDWLKC615"},
            json={
                "company_type": "string",
                "company_website": "string",
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK

        j_resp = response.json()
        assert j_resp == {
            "nz_id": 1002,
            "lei": "549300T6IPOCDWLKC615",
            "legal_name": "Hitachi,Ltd.",
            "jurisdiction": "Japan",
            "company_type": "string",
            "company_website": "string",
            "headquarter_address_lines": "丸の内一丁目6番6号",
            "headquarter_address_number": None,
            "headquarter_city": "東京都 千代田区",
            "headquarter_country": "JP",
            "headquarter_language": "ja",
            "headquarter_postal_code": "100-8280",
            "headquarter_region": None,
            "legal_address_lines": "丸の内一丁目6番6号",
            "legal_address_number": None,
            "legal_city": "東京都 千代田区",
            "legal_country": "JP",
            "legal_language": "ja",
            "legal_postal_code": "100-8280",
            "legal_region": None,
            "sics_sector": "Resource Transformation",
            "sics_sub_sector": "Industrials",
            "sics_industry": "Electrical & Electronic Equipment",
            "created_on": "2023-10-24T09:47:12.926507",
            "last_updated_on": "2023-10-24T09:47:12.926507",
            "active": True,
            "isics": None,
            "duns": None,
            "gleif": None,
            "sing_id": None,
        }
