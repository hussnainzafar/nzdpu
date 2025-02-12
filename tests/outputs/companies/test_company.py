"""
Unit tests for companies endpoint
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app import settings
from app.db.redis import RedisClient
from app.service.core.cache import CoreMemoryCache
from app.service.download_excel_cli_service import SaveExcelFileService
from app.service.dto import CompanyDownloadOutput
from tests.constants import (
    SCHEMA_FILE_NAME,
    SUBMISSION_SCHEMA_COMPANIES_FILE_NAME,
)
from tests.outputs.utils import create_entities
from tests.routers.auth_test import AuthTest
from tests.routers.utils import create_test_form

BASE_ENDPOINT = "/coverage/companies"
data_dir: Path = settings.BASE_DIR.parent / "tests" / "data"


@pytest.fixture
def submission_payload():
    """
    Fixture for submission payload
    Returns
    -------
    submissions payload
    """

    with open(data_dir / SUBMISSION_SCHEMA_COMPANIES_FILE_NAME) as f:
        return {
            "table_view_id": 1,
            "permissions_set_id": 1,
            "values": json.load(f),
        }


class TestCompanies(AuthTest):
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

    @pytest.mark.asyncio
    async def test_list_companies(
        self,
        client: AsyncClient,
        static_cache: CoreMemoryCache,
        session: AsyncSession,
        submission_payload,
    ):
        """
        Test list of companies
        """

        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # insert some organizations
        await self.insert_organization(session)
        # create test permissions
        await self.create_test_permissions(session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        await static_cache.refresh_values()

        # act
        response = await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        j_resp = response.json()

        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}",
            params={
                "name": "Asahi Group Holdings,Ltd.",
                "start": 0,
                "limit": 10,
                "order_by": "legal_name",
                "order": "ASC",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()

        assert j_resp["start"] == 0
        assert j_resp["end"] == 1
        assert type(j_resp["items"]) == list
        assert j_resp["items"][0]["legal_name"] == "Asahi Group Holdings,Ltd."

    @pytest.mark.asyncio
    async def test_download_companies(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
        submission_payload,
    ):
        """
        Test download companies. api
        """

        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # insert some organizations
        await self.insert_organization(session)
        # create test permissions
        await self.create_test_permissions(session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        await static_cache.refresh_values()
        # act
        response = await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        await self.insert_organization(session)
        await static_cache.refresh_values()
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/download",
            params={"name": "Asahi Group Holdings,Ltd."},
        )
        # assert
        assert response.status_code == status.HTTP_200_OK
        # Check the content type of the response
        assert response.headers["content-type"] == "application/octet-stream"

        # Check the filename of the response
        assert (
            response.headers["content-disposition"]
            == 'attachment; filename="nzdpu_companies.csv"'
        )

    @pytest.mark.asyncio
    async def test_historical_emissions_download(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
        submission_payload,
    ):
        # Arrange
        print("Creating test form...")
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        await self.create_test_permissions(session)
        await self.add_admin_permissions_to_user(session)
        print("Inserting organization...")
        await self.insert_organization(session)
        await static_cache.refresh_values()

        # Act: POST to /submissions
        print("Submitting data to /submissions...")
        response = await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        cache = RedisClient(
            settings.cache.host, settings.cache.port, settings.cache.password
        )

        save_excel = SaveExcelFileService(session, static_cache, cache)

        print(f"Submission response: {response.status_code}")
        # Assert POST submission is successful
        assert response.status_code == status.HTTP_200_OK, response.text
        excel_filename = await save_excel.download_company_history_cli(
            nz_id=1001,
        )

        file_path = Path(excel_filename)
        assert file_path.exists(), "Test file does not exist"
        # Read the actual file content
        file_stream = open(file_path, "rb")
        mock_response = CompanyDownloadOutput(file_stream, file_path.name)

        with patch(
            "app.service.company_service.CompanyService.download_companies",
            return_value=mock_response,
        ):
            response = await client.get(
                url=f"{BASE_ENDPOINT}/1001/history/download",
                headers={
                    "content-type": "application/json",
                    "accept": "application/json",
                    "Authorization": f"Bearer {self.access_token}",
                },
            )

        # Assert the response
        assert response.status_code == 200
        assert (
            response.headers["Content-Type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert (
            response.headers["Content-Disposition"]
            == f"attachment; filename={file_path.name}"
        )

        file_stream.seek(0)
        assert response.content == file_stream.read()

    @pytest.mark.asyncio
    async def test_company_emissions(
        self,
        client: AsyncClient,
        session: AsyncSession,
        submission_payload,
        static_cache: CoreMemoryCache,
    ):
        """
        test company disclosures
        """
        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # create test permissions
        await self.create_test_permissions(session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        await self.insert_organization(session)
        await static_cache.refresh_values()
        # act
        response = await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        j_resp = response.json()
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/1001/history",
        )

        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()

        assert j_resp["nz_id"] == 1001
        assert j_resp["model"] is None
        assert j_resp["source"] is None
        # assert all keys are there
        assert not {"reporting_year", "submission"} - set(
            j_resp["history"][0].keys()
        )
        assert j_resp["history"][0]["reporting_year"] == 2020

    @pytest.mark.asyncio
    async def test_report_disclosure(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
        submission_payload,
    ):
        """
        Test report disclosure with start, limit and sort parameters
        """

        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # create test permissions
        await self.create_test_permissions(session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        await self.insert_organization(session)
        await static_cache.refresh_values()
        # act
        response = await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        j_resp = response.json()
        # assert

        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/1001/disclosures",
            params={"start": 0},
        )

        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp["start"] == 0

        assert j_resp["nz_id"] == 1001
        assert len(j_resp["items"]) == 1

        # assert all keys are there
        assert not {"year", "model", "last_updated", "submission_id"} - set(
            j_resp["items"][0].keys()
        )
        assert j_resp["items"][0]["year"] == 2020

    @pytest.mark.asyncio
    async def test_disclosure_details(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
        submission_payload,
    ):
        """
        Test simplest disclosure-details call.
        """
        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # create test permissions
        await self.create_test_permissions(session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        await self.insert_organization(session)
        await static_cache.refresh_values()
        # act
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
        response = await client.get(
            url=f"{BASE_ENDPOINT}/1001/disclosure-details",
            params={"year": 2020},
        )

        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp["values"]
        assert j_resp["units"]

    @pytest.mark.asyncio
    async def test_list_restatement(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
        submission_payload,
    ):
        """
        Test simplest disclosure-details call.
        """
        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # create test permissions
        await self.create_test_permissions(session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        await self.insert_organization(session)

        await static_cache.refresh_values()
        # act
        response = await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text

        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/1001/restatements",
            params={"attribute": "disclosure_source", "year": 2020},
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp["nz_id"] == 1001
        assert type(j_resp["attribute"]) == dict
        assert j_resp["attribute"]["name"] == "disclosure_source"
        assert j_resp["attribute"]["prompt"] == "Disclosure source"
        assert type(j_resp["original"]) == dict
        assert j_resp["original"]["value"] == "CDP Climate Change 2015"

    @pytest.mark.asyncio
    async def test_target_progress(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
        submission_payload,
    ):
        """
        Test simplest disclosure-details call.
        """
        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # create test permissions
        await self.create_test_permissions(session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        await self.insert_organization(session)
        await static_cache.refresh_values()
        # act
        response = await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/1001/targets/progress",
        )

        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
