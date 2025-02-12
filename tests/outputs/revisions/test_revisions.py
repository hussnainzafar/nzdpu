"""Unit tests for revisions router"""

import json
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings
from app.db.models import AuthRole
from app.schemas.enums import SubmissionObjStatusEnum
from app.service.core.cache import CoreMemoryCache
from app.service.submission_builder import SubmissionBuilder
from tests.constants import (
    SCHEMA_FILE_NAME,
    SUBMISSION_SCHEMA_COMPANIES_FILE_NAME,
    SUBMISSION_SCHEMA_FILE_NAME,
)
from tests.routers.auth_test import AuthTest
from tests.routers.utils import create_test_form

BASE_ENDPOINT = "/submissions/revisions"


# pylint: disable = too-many-lines, too-many-public-methods
@pytest.fixture
def submission_payload_revision():
    """
    Fixture for submission payload with revision
    Returns
    -------
    submissions payload
    """
    return {
        "restatements": [
            {
                "path": "org_boundary_approach",
                "reason": "Fixed wrong method",
                "value": "Operational control",
            }
        ],
    }


@pytest.fixture
def submission_payload_revision_second():
    """
    Fixture for submission payload with revision
    Returns
    -------
    submissions payload
    """
    return {
        "restatements": [
            {
                "path": "org_boundary_approach",
                "reason": "Fixed wrong method",
                "value": "Operational control2",
            }
        ],
    }


class TestRevisions(AuthTest):
    """
    Unit tests for revisions APIs
    """

    data_dir: Path = settings.BASE_DIR.parent / "tests/data"
    outputs: Path = (
        settings.BASE_DIR.parent / "tests/outputs/revisions/responses"
    )

    # LIST SUBMISSION REVISIONS

    @pytest.mark.asyncio
    async def test_list_revisions(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test list Revisions API
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
            nz_id=1000,
            table_view_id=1,
            permissions_set_id=set_id,
            tpl_file=SUBMISSION_SCHEMA_FILE_NAME,
            no_change=True,
        )
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/{submission.name}",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        with open(self.outputs / "list.json") as f:
            output_response = json.load(f)

        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        output_response["items"][0]["created_on"] = j_resp["items"][0][
            "created_on"
        ]
        output_response["items"][0]["activated_on"] = j_resp["items"][0][
            "activated_on"
        ]
        output_response["items"][0]["checked_out_on"] = j_resp["items"][0][
            "checked_out_on"
        ]
        output_response["items"][0]["name"] = j_resp["items"][0]["name"]
        # assert (
        #     j_resp["items"][0]["values"]
        #     == output_response["items"][0]["values"]
        # )

    @pytest.mark.asyncio
    async def test_create_revision(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test create Revision API
        """
        # arrange
        form_schema_file = self.data_dir / SCHEMA_FILE_NAME
        await create_test_form(form_schema_file, session)
        # create test permissions
        set_id = await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # create submission
        builder = SubmissionBuilder(
            cache=redis_client, session=session, static_cache=static_cache
        )
        submission = await builder.generate(
            nz_id=1000,
            table_view_id=1,
            permissions_set_id=set_id,
            tpl_file=SUBMISSION_SCHEMA_FILE_NAME,
            no_change=True,
        )
        # set it checked out
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/edit",
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
            url=f"{BASE_ENDPOINT}/{submission.name}",
            json=revision_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()

        # USE ME IF NEED TO REBUILD THE RESPONSE
        # with open(self.outputs / "create.json", "w") as f:
        #     resp = json.dumps(j_resp, indent=4, default=str)
        #     f.write(resp)

        with open(self.outputs / "create.json") as f:
            output_response = json.load(f)
        output_response["created_on"] = j_resp["created_on"]
        output_response["activated_on"] = j_resp["activated_on"]
        output_response["checked_out_on"] = j_resp["checked_out_on"]
        output_response["name"] = j_resp["name"]
        assert j_resp["values"] == output_response["values"]

    @pytest.mark.asyncio
    async def test_get_revision(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        submission_payload_revision,
        static_cache: CoreMemoryCache,
    ):
        """
        Test get Revisions API
        """
        self.data_dir: Path = settings.BASE_DIR.parent / "tests" / "data"
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
            nz_id=1000,
            table_view_id=1,
            permissions_set_id=set_id,
            tpl_file=SUBMISSION_SCHEMA_FILE_NAME,
            no_change=True,
        )

        # set it checked out
        await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/edit",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # create revision
        await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}",
            json=submission_payload_revision,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/{submission.name}/2",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK

        j_resp = response.json()
        # USE ME IF NEED TO REBUILD THE RESPONSE
        # with open(self.outputs / "get.json", "w") as f:
        #     resp = json.dumps(j_resp, indent=4, default=str)
        #     f.write(resp)

        with open(self.outputs / "get.json") as f:
            output_response = json.load(f)

        output_response["created_on"] = j_resp["created_on"]
        output_response["activated_on"] = j_resp["activated_on"]
        output_response["checked_out_on"] = j_resp["checked_out_on"]
        output_response["name"] = j_resp["name"]
        assert j_resp["values"] == output_response["values"]

    @pytest.mark.asyncio
    async def test_edit_mode_revisions(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test list Revisions API
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
            nz_id=1000,
            table_view_id=1,
            permissions_set_id=set_id,
            tpl_file=SUBMISSION_SCHEMA_FILE_NAME,
            no_change=True,
        )
        # set it checked out
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/edit",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()

        assert j_resp["id"] == 1
        assert j_resp["checked_out"] == True
        assert j_resp["user_id"] == 1
        assert datetime.fromisoformat(j_resp["checked_out_on"])
        assert j_resp["name"] == submission.name

    @pytest.mark.asyncio
    async def test_clear_edit_mode(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test clear edit mode for a checked out submission.
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
            nz_id=1000,
            table_view_id=1,
            permissions_set_id=set_id,
            tpl_file=SUBMISSION_SCHEMA_FILE_NAME,
            no_change=True,
        )
        # set it checked out once
        await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/edit",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/edit/clear",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert j_resp["id"] == 1
        assert j_resp["name"] == submission.name
        assert j_resp["checked_out"] == False
        assert j_resp["user_id"] == None
        assert j_resp["checked_out_on"] == None

    @pytest.mark.asyncio
    async def test_rollback_submission(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test list Revisions API
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
            nz_id=1000,
            table_view_id=1,
            permissions_set_id=set_id,
            tpl_file=SUBMISSION_SCHEMA_FILE_NAME,
            no_change=True,
        )
        # set it checked out
        await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/edit",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # create revision
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}",
            json={
                "restatements": [
                    {
                        "path": "org_boundary_approach",
                        "reason": "example",
                        "value": 102,
                    }
                ],
            },
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/rollback",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp["active_id"] == 1
        assert j_resp["active_revision"] == 1
        assert j_resp["prev_active_id"] == 2
        assert j_resp["prev_active_revision"] == 2
        assert j_resp["name"] == submission.name

    @pytest.mark.asyncio
    async def test_save_submission_as_draft(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test "the save submission as draft" endpoint.
        """
        # arrange

        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # create test permissions
        set_id = await self.create_test_permissions(session)
        # create submission
        builder = SubmissionBuilder(
            cache=redis_client, session=session, static_cache=static_cache
        )
        submission = await builder.generate(
            nz_id=1000,
            table_view_id=1,
            permissions_set_id=set_id,
            tpl_file=SUBMISSION_SCHEMA_FILE_NAME,
            no_change=True,
        )
        assert submission.revision == 1
        # set it checked out
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/edit",
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
        draft_req = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/draft",
            json=revision_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert draft_req.status_code == status.HTTP_200_OK, draft_req.text
        draft = draft_req.json()
        assert draft["status"] == SubmissionObjStatusEnum.DRAFT

    @pytest.mark.asyncio
    async def test_submission_publish(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test "the save submission as draft" endpoint.
        """
        # arrange

        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        # create test permissions
        set_id = await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # create submission
        builder = SubmissionBuilder(
            cache=redis_client, session=session, static_cache=static_cache
        )
        submission = await builder.generate(
            nz_id=1000,
            table_view_id=1,
            permissions_set_id=set_id,
            tpl_file=SUBMISSION_SCHEMA_COMPANIES_FILE_NAME,
            no_change=True,
        )
        assert submission.revision == 1
        # set it checked out
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/edit?force=false",
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
        draft_req = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/draft",
            json=revision_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert draft_req.status_code == status.HTTP_200_OK, draft_req.text
        draft = draft_req.json()
        assert draft["status"] == SubmissionObjStatusEnum.DRAFT

        # act
        publish_req = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/publish",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert publish_req.status_code == status.HTTP_200_OK, publish_req.text
        published = publish_req.json()

        assert published["id"] == 1
        assert published["revision"] == 1
        assert published["name"] == submission.name
        assert published["status"] == SubmissionObjStatusEnum.PUBLISHED
        assert published["restatements"] == [
            {
                "attribute_name": (
                    "s1_emissions_exclusion_dict"
                    ".{::0}"
                    ".s1_emissions_exclusion_perc"
                ),
                "attribute_row": 1,
                "reason_for_restatement": "Changed value",
            }
        ]
