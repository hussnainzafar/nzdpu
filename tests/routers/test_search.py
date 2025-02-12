"""Test Search"""

import json
from pathlib import Path

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings
from app.db.models import AuthRole, Organization
from app.schemas.enums import SICSSectorEnum
from app.schemas.search import (
    SearchDSLMetaElement,
    SearchDSLSortOptions,
    SearchQuery,
    SortOrderEnum,
)
from app.service.core.cache import CoreMemoryCache
from app.service.submission_builder import SubmissionBuilder
from tests.constants import SCHEMA_FILE_NAME, SUBMISSION_SCHEMA_FILE_NAME
from tests.routers.auth_test import AuthTest

from .utils import NZ_ID, create_test_form

BASE_ENDPOINT = "/search"


@pytest.fixture
def submission_payload():
    """
    Fixture for submission payload
    Returns
    -------
    submissions payload
    """
    data_dir: Path = settings.BASE_DIR.parent / "tests" / "data"
    with open(data_dir / SUBMISSION_SCHEMA_FILE_NAME, encoding="utf-8") as f:
        return {
            "nz_id": NZ_ID,
            "table_view_id": 1,
            "permissions_set_id": 1,
            "values": json.load(f),
        }


@pytest.fixture
def search_query():
    return SearchQuery(
        meta=SearchDSLMetaElement(
            reporting_year=[2020],
            data_model=["NZDPU Core"],
            jurisdiction=["US-MA"],
            sics_sector=["Infrastructure"],
            sics_sub_sector=["subsector"],
            sics_industry=["sics_industry"],
        ),
        fields=["sics_sector", "sics_sub_sector", "sics_industry"],
    )


class TestSearch(AuthTest):
    """
    Unit tests for Search API.
    """

    data_dir: str = f"{settings.BASE_DIR}/../tests/data"

    @pytest.mark.asyncio
    async def test_search_single_table_single_match(
        self,
        client: AsyncClient,
        static_cache: CoreMemoryCache,
        session: AsyncSession,
        submission_payload: dict,
        search_query: SearchQuery,
    ):
        """
        Test search with only one queried table and "match"
        statement.
        """

        # arrange
        # create forms and submission
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await static_cache.refresh_values()
        # create test permissions
        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # create submission
        response = await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text

        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            params={"view_id": 1},
            json=search_query.model_dump(),
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp["items"]
        assert j_resp["items"][0]["data_model"] == "NZDPU Core"
        assert int(j_resp["items"][0]["reporting_year"]) == 2020
        assert j_resp["items"][0]["legal_name"] == "testorg"
        assert j_resp["items"][0]["jurisdiction"] == "US-MA"
        assert j_resp["items"][0]["lei"] == "000012345678"
        assert (
            j_resp["items"][0]["sics_sector"] == SICSSectorEnum.INFRASTRUCTURE
        )
        assert j_resp["items"][0]["sics_sub_sector"] == "subsector"
        assert j_resp["items"][0]["sics_industry"] == "sics_industry"

    @pytest.mark.asyncio
    async def test_search_single_table_with_sort_field_only_ascending(
        self,
        client: AsyncClient,
        static_cache: CoreMemoryCache,
        session: AsyncSession,
        submission_payload: dict,
        search_query: SearchQuery,
    ):
        """
        Test search with only one queried table and sorting field
        without options (default ascending order).

        Creates two submissions, one with "company1" and one with
        "company2" for `company_name`. Asserts that results are ordered
        in ascending order.
        """

        # arrange
        # create forms and submission
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        # create test permissions
        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # create first submission
        await static_cache.refresh_values()
        response = await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        # create second submission
        submission_payload["values"]["date_end_reporting_year"] = (
            "2017-12-12T05:34:22.000Z"
        )
        submission_payload["values"]["reporting_year"] = 2017
        submission_payload["values"]["total_s1_emissions_ghg"] = 1094879
        submission_payload["values"]["organization_identifier"] = 1000
        response = await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        # create second user
        organization = Organization(
            nz_id=1001,
            lei="87654321000",
            legal_name="testorg2",
            jurisdiction="US-MA",
            sics_sector=SICSSectorEnum.INFRASTRUCTURE,
            sics_sub_sector="subsector",
            sics_industry="sics_industry",
        )
        session.add(organization)
        await session.flush()
        new_token = await self.create_more_users(
            client=client,
            session=session,
            user_name="testname",
            user_pass="userpass",
            organization_id=organization.id,
        )
        await self.add_role_to_user(
            session=session,
            role_name=AuthRole.ADMIN,
            user_name="testname",
        )
        # create third submission
        submission_payload["values"]["legal_entity_identifier"] = (
            organization.lei
        )
        submission_payload["values"]["reporting_year"] = 2021
        submission_payload["values"]["organization_identifier"] = 1001
        submission_payload["values"]["total_s1_emissions_ghg"] = 1094880
        await static_cache.refresh_values()
        response = await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {new_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        # create fourth submission
        submission_payload["values"]["legal_entity_identifier"] = (
            organization.lei
        )
        submission_payload["values"]["reporting_year"] = 2022
        submission_payload["values"]["total_s1_emissions_ghg"] = 1094881

        response = await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {new_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text

        # build search request payload
        search_query.sort = [
            "reporting_year",
            "total_s1_emissions_ghg",
        ]
        search_query.meta.reporting_year.extend([2017, 2021, 2022])
        search_query.fields = ["reporting_year", "total_s1_emissions_ghg"]

        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            params={"view_id": 1},
            json=search_query.model_dump(),
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp["items"]
        assert len(j_resp["items"]) == 4
        first_submission = j_resp["items"][0]
        second_submission = j_resp["items"][1]
        third_submission = j_resp["items"][2]
        assert j_resp["items"][0]["data_model"] == "NZDPU Core"
        assert int(first_submission["reporting_year"]) == 2017
        assert int(second_submission["reporting_year"]) == 2020
        assert int(third_submission["reporting_year"]) == 2021
        assert first_submission["legal_name"] == "testorg"
        assert first_submission["jurisdiction"] == "US-MA"

        assert (
            first_submission["reporting_year"]
            < second_submission["reporting_year"]
        )
        assert (
            second_submission["reporting_year"]
            < third_submission["reporting_year"]
        )

        assert (
            first_submission["total_s1_emissions_ghg"]
            < second_submission["total_s1_emissions_ghg"]
        )
        assert (
            second_submission["total_s1_emissions_ghg"]
            > third_submission["total_s1_emissions_ghg"]
        )

    @pytest.mark.asyncio
    async def test_search_single_table_with_sort_object_descending(
        self,
        client: AsyncClient,
        static_cache: CoreMemoryCache,
        session: AsyncSession,
        submission_payload: dict,
        search_query: SearchQuery,
    ):
        """
        Test search with only one queried table and sorting field
        with options specifying descending order.

        Creates two submissions, one with "company1" and one with
        "company2" for `company_name`. Asserts that results are ordered
        in descending order.
        """

        # arrange
        # create forms and submission
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await static_cache.refresh_values()
        # create test permissions
        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # create first submission
        await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # create second submission
        submission_payload["values"]["date_end_reporting_year"] = (
            "2017-12-12T05:34:22.000Z"
        )
        submission_payload["values"]["reporting_year"] = 2017
        await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # build search request payload
        search_query.sort = [
            {"reporting_year": SearchDSLSortOptions(order=SortOrderEnum.DESC)}
        ]
        search_query.meta.reporting_year.append(2017)

        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            params={"view_id": 1},
            json=search_query.model_dump(),
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp["items"]
        assert len(j_resp["items"]) == 2
        assert int(j_resp["items"][0]["reporting_year"]) == 2020
        assert int(j_resp["items"][1]["reporting_year"]) == 2017
        assert j_resp["items"][0]["legal_name"] == "testorg"
        assert j_resp["items"][0]["jurisdiction"] == "US-MA"
        assert (
            j_resp["items"][0]["reporting_year"]
            > j_resp["items"][1]["reporting_year"]
        )

    @pytest.mark.asyncio
    async def test_search_single_table_single_match_offset_limit_no_results(
        self,
        client: AsyncClient,
        static_cache: CoreMemoryCache,
        session: AsyncSession,
        submission_payload: dict,
        search_query: SearchQuery,
    ):
        """
        Test search with only one queried table and "match"
        statement. Set offset to 1 and limit to 1. Should retrieve no
        results (with only one submission).
        """

        # arrange
        # create forms and submission
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await static_cache.refresh_values()
        # create test permissions
        await self.create_test_permissions(session)
        # create submission
        await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        response = await client.post(
            url=BASE_ENDPOINT,
            params={
                "view_id": 1,
                "start": 1,
                "limit": 1,
            },
            json=search_query.model_dump(),
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp["start"] == 1
        assert j_resp["size"] == 0
        assert not j_resp["items"]

    @pytest.mark.asyncio
    async def test_search_limit_page_size(
        self,
        client: AsyncClient,
        static_cache: CoreMemoryCache,
        session: AsyncSession,
        submission_payload: dict,
        search_query: SearchQuery,
    ):
        """
        Test search with only one queried table and "match"
        statement. Set offset to 1 and limit to 1. Should retrieve no
        results (with only one submission).
        """

        # arrange
        # create forms and submission
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await static_cache.refresh_values()
        # create test permissions
        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # create first submission
        await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # create second submission
        submission_payload["values"]["date_end_reporting_year"] = (
            "2017-12-12T05:34:22.000Z"
        )
        submission_payload["values"]["reporting_year"] = 2017
        await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # build search request payload
        search_query.sort = [
            {"reporting_year": SearchDSLSortOptions(order=SortOrderEnum.DESC)}
        ]
        search_query.meta.reporting_year.append(2017)

        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            params={"view_id": 1, "start": 0, "limit": 3},
            json=search_query.model_dump(),
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp["size"] == 2

        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            params={"view_id": 1, "start": 0, "limit": 2},
            json=search_query.model_dump(),
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp["size"] == 2

    @pytest.mark.asyncio
    async def test_search_with_single_quote_value_in_jurisdiction(
        self,
        client: AsyncClient,
        static_cache: CoreMemoryCache,
        session: AsyncSession,
        submission_payload: dict,
        search_query: SearchQuery,
    ):
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await static_cache.refresh_values()
        # create test permissions
        await self.create_test_permissions(session)
        # create submission
        await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        search_query.meta.jurisdiction = [
            "Côte d'Ivoire",
            "Democratic People's Republic of Korea",
            "Lao People's Democratic Republic",
        ]
        response = await client.post(
            url=BASE_ENDPOINT,
            params={"view_id": 1},
            json=search_query.model_dump(),
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text

    @pytest.mark.asyncio
    async def test_search_single_table_single_match_no_results(
        self,
        client: AsyncClient,
        static_cache: CoreMemoryCache,
        session: AsyncSession,
        submission_payload: dict,
        search_query: SearchQuery,
    ):
        """
        Test search with only one queried table. This test should return
        no results, since we are querying for a non-existing
        jurisdiction.
        """

        # arrange
        # create forms and submission
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await static_cache.refresh_values()
        # create test permissions
        await self.create_test_permissions(session)
        # create submission
        await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        search_query.meta.jurisdiction = ["nonexistent"]

        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            params={"view_id": 1},
            json=search_query.model_dump(),
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert not j_resp["items"]

    @pytest.mark.asyncio
    async def test_search_invalid_view_id_raises_error(
        self,
        client: AsyncClient,
        static_cache: CoreMemoryCache,
        session: AsyncSession,
        submission_payload: dict,
        search_query: SearchQuery,
    ):
        """
        Test search with only one queried table and "match"
        statement.
        """

        # arrange
        # create forms and submission
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await static_cache.refresh_values()
        # create test permissions
        await self.create_test_permissions(session)
        # create submission
        await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            params={"view_id": 999},
            json=search_query.model_dump(),
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_404_NOT_FOUND, response.text
        j_resp = response.json()
        assert j_resp["detail"] == {"view_id": "Table view not found."}

    @pytest.mark.asyncio
    async def test_search_with_fields(
        self,
        client: AsyncClient,
        static_cache: CoreMemoryCache,
        session: AsyncSession,
        search_query: SearchQuery,
        redis_client,
        submission_payload: dict,
    ):
        """
        Test search with field filter.
        """

        # arrange
        # create forms and submission
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await static_cache.refresh_values()
        # create test permissions
        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # create submission
        response = await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text

        search_query.fields = [
            "sics_sector",
            "sics_sub_sector",
            "sics_industry",
            "org_boundary_approach",
            "total_s1_emissions_ghg",
            (
                "s1_emissions_exclusion_dict"
                ".{::0}"
                ".s1_emissions_exclusion_perc"
            ),
            ("s1_other_ghg_emissions_dict" ".{::0}" ".s1_other_ghg_emissions"),
            ("s1_other_ghg_emissions_dict" ".{::1}" ".s1_other_ghg_emissions"),
            (
                "s3_ghgp_c1_emissions_method_dict"
                ".{::0}"
                ".s3_ghgp_c1_emissions_method_perc"
            ),
            "s3_ghgp_c1_emissions_method_dict.{::1}.s3_ghgp_c1_emissions_method_perc",
        ]

        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            params={"view_id": 1, "limit": 1},
            json=search_query.model_dump(),
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp["items"] == [
            {
                "org_boundary_approach": "Operational control",
                "total_s1_emissions_ghg": 1094881.0,
                "s1_emissions_exclusion_dict": [
                    {"s1_emissions_exclusion_perc": 0.1}
                ],
                "s1_other_ghg_emissions_dict": [
                    {"s1_other_ghg_emissions": 1021.0},
                    {"s1_other_ghg_emissions": 2032.0},
                ],
                "s3_ghgp_c1_emissions_method_dict": [
                    {"s3_ghgp_c1_emissions_method_perc": 20.0},
                    {"s3_ghgp_c1_emissions_method_perc": 40.0},
                ],
                "sics_industry": "sics_industry",
                "nz_id": 1000,
                "data_model": "NZDPU Core",
                "jurisdiction": "US-MA",
                "sics_sub_sector": "subsector",
                "reporting_year": 2020,
                "lei": "000012345678",
                "sics_sector": "Infrastructure",
                "legal_name": "testorg",
                "id": 1,
            }
        ]
