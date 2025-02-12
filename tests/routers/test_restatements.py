"""Unit tests for restatements router"""

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings
from app.db.models import AuthRole
from app.service.core.cache import CoreMemoryCache
from app.service.submission_builder import SubmissionBuilder
from tests.constants import SCHEMA_FILE_NAME, SUBMISSION_SCHEMA_FILE_NAME
from tests.routers.auth_test import AuthTest

from .utils import NZ_ID, create_test_form

# pylint: disable = too-many-lines, too-many-public-methods
BASE_ENDPOINT = "/coverage/companies"


class TestRestatementsList(AuthTest):
    """
    Unit tests for restatements APIs
    """

    data_dir: str = f"{settings.BASE_DIR}/../tests/data"

    # LIST SUBMISSION REVISIONS

    @pytest.mark.asyncio
    async def test_list_restatements(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test list Restatements API
        """
        # arrange
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # create test permissions
        set_id: int = await self.create_test_permissions(session)
        # create submission
        builder = SubmissionBuilder(
            cache=redis_client, session=session, static_cache=static_cache
        )
        submission = await builder.generate(
            table_view_id=1,
            permissions_set_id=set_id,
            tpl_file=SUBMISSION_SCHEMA_FILE_NAME,
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
            url=f"/submissions/revisions/{submission.name}",
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
            url=f"/submissions/revisions/{submission.name}",
            json=revision_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/{NZ_ID}/restatements",
            params={
                "attribute": (
                    "s1_emissions_exclusion_dict"
                    ".{::0}"
                    ".s1_emissions_exclusion_perc"
                ),
                "year": 2020,
                "form": "nzdpu_form",
                "row": 1,
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert j_resp["nz_id"] == NZ_ID
        assert (
            j_resp["attribute"]["name"] == "s1_emissions_exclusion_dict"
            ".{::0}"
            ".s1_emissions_exclusion_perc"
        )
        assert len(j_resp["restatements"]) == 2
        assert j_resp["restatements"][0]["value"] == 80.0
        assert j_resp["restatements"][0]["reason"] == "Changed value"

    @pytest.mark.asyncio
    async def test_list_restatements_with_wrong_parameter(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test list Restatements API when wrong parameter is sent
        """
        # arrange
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # create test permissions
        set_id: int = await self.create_test_permissions(session)
        # create submission
        builder = SubmissionBuilder(
            cache=redis_client, session=session, static_cache=static_cache
        )
        submission = await builder.generate(
            nz_id=NZ_ID,
            table_view_id=1,
            permissions_set_id=set_id,
            tpl_file=SUBMISSION_SCHEMA_FILE_NAME,
            no_change=True,
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
            url=f"/submissions/revisions/{submission.name}",
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
            url=f"/submissions/revisions/{submission.name}",
            json=revision_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/{NZ_ID}/restatements",
            params={
                "attribute": "target_abs.wrong.tgt_abs_coverage_sector",
                "year": 2019,
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        j_resp = response.json()
        assert j_resp["detail"] == {
            "restatements": (
                "Wrong attribute field path:"
                " 'target_abs.wrong.tgt_abs_coverage_sector'"
            )
        }

    @pytest.mark.asyncio
    async def test_list_restatements_not_valid_attribute(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test list Restatements API with not valid attribute
        """
        # arrange
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        # create test permissions
        set_id: int = await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # create submission
        builder = SubmissionBuilder(
            cache=redis_client, session=session, static_cache=static_cache
        )
        submission = await builder.generate(
            nz_id=NZ_ID,
            table_view_id=1,
            permissions_set_id=set_id,
            tpl_file=SUBMISSION_SCHEMA_FILE_NAME,
            no_change=True,
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
        # create revision
        revision_payload = {
            "restatements": [
                {
                    "path": "org_boundary_approach",
                    "reason": "Fixed wrong method",
                    "value": 106,
                }
            ]
        }
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
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/{NZ_ID}/restatements",
            params={
                "attribute": "organizational_boundary",
                "year": 2019,
                "form": "nzdpu_form",
                "row": 1,
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        j_resp = response.json()
        assert j_resp["detail"] == {
            "attribute": (
                "Column definition for 'organizational_boundary'"
                " in table_def could not be found."
            )
        }

    @pytest.mark.asyncio
    async def test_list_restatements_for_undefined_company(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test list Restatements API with not valid lei
        """
        # arrange
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        # create test permissions
        set_id: int = await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # create submission
        builder = SubmissionBuilder(
            cache=redis_client, session=session, static_cache=static_cache
        )
        submission = await builder.generate(
            nz_id=NZ_ID,
            table_view_id=1,
            permissions_set_id=set_id,
            tpl_file=SUBMISSION_SCHEMA_FILE_NAME,
            no_change=True,
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
        # create revision
        revision_payload = {
            "restatements": [
                {
                    "path": "org_boundary_approach",
                    "reason": "Fixed wrong method",
                    "value": 106,
                }
            ]
        }
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
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/123456789/restatements",
            params={
                "attribute": "org_boundary_approach",
                "year": 2019,
                "form": "nzdpu_form",
                "row": 1,
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        j_resp = response.json()
        assert j_resp["detail"] == {
            "nz_id": "No submissions found for given nz_id '123456789'"
        }
