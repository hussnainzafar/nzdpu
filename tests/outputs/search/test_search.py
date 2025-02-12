"""Test Search"""

import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings
from app.schemas.search import SearchDSLMetaElement, SearchQuery
from app.service.core.cache import CoreMemoryCache
from app.service.submission_builder import SubmissionBuilder
from tests.constants import (
    SCHEMA_FILE_NAME,
    SUBMISSION_SCHEMA_COMPANIES_FILE_NAME,
)
from tests.outputs.utils import create_entities
from tests.routers.auth_test import AuthTest
from tests.routers.utils import NZ_ID, create_test_form

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
    with open(data_dir / SUBMISSION_SCHEMA_COMPANIES_FILE_NAME) as f:
        return {
            "table_view_id": 1,
            "permissions_set_id": 1,
            "values": json.load(f),
        }


@pytest.fixture
def search_query():
    return SearchQuery(
        meta=SearchDSLMetaElement(
            reporting_year=[2020, 2021, 2022],
            data_model=["NZDPU Core"],
            jurisdiction=["US-MA"],
        ),
        fields=["sics_sector", "sics_subsector", "sics_industry"],
        sort=["data_model", "legal_name"],
    )


@pytest.fixture
def items_data():
    return [
        {
            "data_model": "NZDPU Core",
            "reporting_year": 2020,
            "org_boundary_approach": "Operational control",
            "total_s1_emissions_ghg": 1094881.0,
            "s1_emissions_exclusion": [{"s1_emissions_exclusion_perc": 0.1}],
            "s1_other_ghg_emissions_f": [
                {"s1_other_ghg_emissions": 1021.0},
                {"s1_other_ghg_emissions": 2032.0},
            ],
            "s3_ghgp_c1_emissions_method": [
                {"s3_ghgp_c1_emissions_method_perc": 20.0},
                {"s3_ghgp_c1_emissions_method_perc": 40.0},
            ],
            "legal_name": "testorg",
            "lei": "000012345678",
            "nz_id": NZ_ID,
            "sics_industry": "sics_industry",
            "sics_sector": "Infrastructure",
            "jurisdiction": "US-MA",
            "sics_sub_sector": "subsector",
            "id": 1,
        }
    ]


class TestSearch(AuthTest):
    @staticmethod
    async def insert_organization(session: AsyncSession):
        try:
            df = pd.read_csv("tests/outputs/companies/data/organizations.csv")
            entities = create_entities(df)
            session.add_all(entities)
            # commit the transaction
            await session.commit()

        except Exception as e:
            print(f"Error during insertion: {e}")
            # Rollback the transaction in case of an error
            await session.rollback()
        finally:
            # Close the session
            await session.close()

    """
    Unit tests for Search API.
    """

    data_dir: str = f"{settings.BASE_DIR}/../tests/data"

    @pytest.mark.asyncio
    async def test_search(
        self,
        client: AsyncClient,
        static_cache: CoreMemoryCache,
        session: AsyncSession,
        search_query: SearchQuery,
        redis_client,
        submission_payload,
    ):
        """
        Test search with field filter.
        """

        # arrange
        # create forms and submission
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        # create test permissions
        # insert some organizations
        await self.insert_organization(session)
        # create test permissions
        await self.create_test_permissions(session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        await static_cache.refresh_values()
        await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        search_query.fields = [
            "legal_name",
            "lei",
            "data_model",
            "reporting_year",
            "jurisdiction",
            "sics_sector",
            "sics_sub_sector",
            "org_boundary_approach",
            "sics_industry",
            "total_s1_emissions_ghg",
            ("s1_emissions_exclusion" ".{::0}" ".s1_emissions_exclusion_perc"),
            ("s1_other_ghg_emissions_f" ".{::0}" ".s1_other_ghg_emissions"),
            ("s1_other_ghg_emissions_f" ".{::1}" ".s1_other_ghg_emissions"),
            (
                "s3_ghgp_c1_emissions_method"
                ".{::0}"
                ".s3_ghgp_c1_emissions_method_perc"
            ),
            "s3_ghgp_c1_emissions_method.{::1}.s3_ghgp_c1_emissions_method_perc",
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
        assert j_resp["items"]

    @pytest.mark.asyncio
    async def test_search_download(
        self,
        config,
        client: AsyncClient,
        static_cache: CoreMemoryCache,
        session: AsyncSession,
        search_query: SearchQuery,
        redis_client,
        items_data,
        submission_payload,
    ):
        """
        Test search with field filter.
        """

        # arrange
        # create forms and submission
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        # create test permissions
        set_id = await self.create_test_permissions(session)
        await self.add_admin_permissions_to_user(session)

        # create submission
        builder = SubmissionBuilder(
            cache=redis_client, session=session, static_cache=static_cache
        )
        # create submission

        submission = await builder.generate(
            table_view_id=1,
            permissions_set_id=set_id,
            tpl_file=SUBMISSION_SCHEMA_COMPANIES_FILE_NAME,
            no_change=True,
            nz_id=NZ_ID,
        )

        # set it checked out

        response = await client.post(
            url=f"/submissions/revisions/{submission.name}/edit",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        data = response.json()
        # create revision
        revision_payload = {
            "restatements": [
                {
                    "path": (
                        "s1_emissions_exclusion_dict"
                        ".{::0}"
                        ".s1_emissions_exclusion_perc"
                    ),
                    "reason": "Changed value",
                    "value": 80,
                }
            ]
        }
        response = await client.post(
            url=f"/submissions/revisions/{data.get('name')}",
            json=revision_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        # create revision
        revision_payload = {
            "restatements": [
                {
                    "path": "org_boundary_approach",
                    "reason": "Fixed wrong method",
                    "value": 105,
                }
            ]
        }

        await client.post(
            url=f"/submissions/revisions/{submission.name}/edit?force=false",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        response = await client.post(
            url=f"/submissions/revisions/{submission.name}",
            json=revision_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        await static_cache.refresh_values()

        search_query.fields = []
        # act
        response = await client.post(
            url=BASE_ENDPOINT + "/download",
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
        assert response.status_code == status.HTTP_200_OK
        assert (
            response.headers["Content-Type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        # save file
