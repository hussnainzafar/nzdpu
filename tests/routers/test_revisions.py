"""Unit tests for revisions router"""

from pathlib import Path

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings
from app.db.models import AuthRole, Permission
from app.schemas.enums import SubmissionObjStatusEnum
from app.service.core.cache import CoreMemoryCache
from app.service.core.utils import strip_none
from app.service.submission_builder import SubmissionBuilder
from tests.constants import SCHEMA_FILE_NAME, SUBMISSION_SCHEMA_FILE_NAME
from tests.routers.auth_test import AuthTest

from .utils import NZ_ID, create_test_form

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


class TestRevisionsList(AuthTest):
    """
    Unit tests for revisions APIs
    """

    data_dir: str = f"{settings.BASE_DIR}/../tests/data"

    # LIST SUBMISSION REVISIONS

    @pytest.mark.asyncio
    async def test_list_revisions(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
        redis_client,
        submission_payload_revision,
        submission_payload_revision_second,
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
            nz_id=NZ_ID,
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
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}",
            json=submission_payload_revision,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        # create revision
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}",
            json=submission_payload_revision_second,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/{submission.name}",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert len(j_resp["items"]) == 3
        assert j_resp["items"][0]["values"]
        assert j_resp["items"][0]["revision"] == 3
        assert j_resp["items"][0]["active"]
        assert (
            j_resp["items"][0]["values"]["org_boundary_approach"]
            == "Operational control2"
        )
        assert j_resp["items"][1]["revision"] == 2
        assert not j_resp["items"][1]["active"]
        assert (
            j_resp["items"][1]["values"]["org_boundary_approach"]
            == "Operational control"
        )
        assert j_resp["items"][2]["revision"] == 1
        assert not j_resp["items"][2]["active"]

    @pytest.mark.asyncio
    async def test_list_revisions_active_false_no_result(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test list Revisions API with active parameter set to False.
        Returns an empty "items" list because all submissions and
        revisions have active=True by default.
        """
        # arrange
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        # create submission
        builder = SubmissionBuilder(
            cache=redis_client, session=session, static_cache=static_cache
        )
        submission = await builder.generate(
            nz_id=NZ_ID,
            table_view_id=1,
            tpl_file=SUBMISSION_SCHEMA_FILE_NAME,
            no_change=True,
        )
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # set it checked out
        await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/edit",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/{submission.name}",
            params={"active": False},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert not j_resp["items"]

    @pytest.mark.asyncio
    async def test_list_revisions_active_false(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
        redis_client,
        submission_payload_revision,
        submission_payload_revision_second,
    ):
        """
        Test list Revisions API with active parameter set to False.
        Returns an empty "items" list because all submissions and
        revisions have active=True by default.
        """
        # arrange
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
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
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # set it checked out
        await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/edit",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # create first revision
        await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}",
            json=submission_payload_revision,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
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
        # create second revision
        await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}",
            json=submission_payload_revision_second,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
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
        # act
        # create third revision
        response = await client.get(
            url=f"{BASE_ENDPOINT}/{submission.name}",
            params={"active": False},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert len(j_resp["items"]) == 2
        assert j_resp["items"][0]["active"] is False
        assert j_resp["items"][1]["active"] is False

    @pytest.mark.asyncio
    async def test_list_revisions_invalid_submission_name(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
    ):
        """
        Test list Revisions API with invalid submission name.
        Should return a 404 Not Found response.
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/invalid_submission_name",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert j_resp["items"] == []

    @pytest.mark.asyncio
    async def test_list_revisions_empty_database(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
    ):
        """
        Test list Revisions API with an empty database.
        Should return an empty "items" list.
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/dummy_submission_name",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert not j_resp["items"]


class TestRevisionsGet(AuthTest):
    """
    Unit tests for revisions APIs
    """

    data_dir: Path = settings.BASE_DIR.parent / "tests" / "data"

    @pytest.mark.asyncio
    async def test_get_revision(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
        redis_client,
        submission_payload_revision,
    ):
        """
        Test get Revisions API
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
        assert j_resp["revision"] == 2
        assert (
            j_resp["values"]["org_boundary_approach"] == "Operational control"
        )

    @pytest.mark.asyncio
    async def test_get_non_existent_submission(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
    ):
        """
        Test get Revisions API with non existent submission.
        Should return a 404 Not Found response.
        """
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        response = await client.get(
            url=f"{BASE_ENDPOINT}/non_existent_submission/1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_non_existent_revision(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test get Revisions API with non existent revision.
        Should return a 404 Not Found response.
        """
        # arrange
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
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
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/{submission.name}/9999",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestRevisionsCreate(AuthTest):
    """
    Unit tests for revisions APIs
    """

    data_dir: Path = settings.BASE_DIR.parent / "tests" / "data"

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
            nz_id=NZ_ID,
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
        first_revision = response.json()
        strip_none(submission.values)
        strip_none(first_revision["values"])

    @pytest.mark.asyncio
    async def test_create_revision_no_data_raises_422(
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
            url=f"{BASE_ENDPOINT}/{submission.name}",
            json={"restatements": []},
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        j_resp = response.json()
        assert j_resp["detail"] == {"data": "No value submitted!"}

    @pytest.mark.asyncio
    async def test_create_revision_invalid_fields_throw_error(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test create Revision API. Invalid fields for a form raise error.
        """
        # arrange
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        # create test permissions
        set_id: int = await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.ADMIN)
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
            url=f"{BASE_ENDPOINT}/{submission.name}",
            json={
                "restatements": [
                    {
                        "path": "foo",
                        "reason": "test",
                        "value": "example",
                    }
                ],
            },
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_404_NOT_FOUND, response.text
        j_resp = response.json()
        assert j_resp["detail"] == {
            "restatements": "No column def found for attribute 'foo'"
        }

    @pytest.mark.asyncio
    async def test_create_revision_invalid_text_constraint(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test create Revision API with invalid text data.
        """
        # arrange
        await create_test_form(f"{self.data_dir}/form-create.json", session)
        # create test permissions
        set_id: int = await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.ADMIN)
        await static_cache.refresh_values()

        # create submission
        builder = SubmissionBuilder(
            cache=redis_client, session=session, static_cache=static_cache
        )
        submission = await builder.generate(
            nz_id=NZ_ID,
            table_view_id=1,
            permissions_set_id=set_id,
            tpl_file="form-create-sub.json",
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
        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}",
            json={
                "restatements": [
                    {
                        "path": "data_model",
                        "reason": "example",
                        "value": "foo",
                    }
                ],
            },
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        j_resp = response.json()
        assert j_resp["reason"] == "Constraints validation error."
        assert j_resp["loc"] == "data_model"
        assert j_resp["value"] == "foo"
        assert "constraint_action" in j_resp

    @pytest.mark.asyncio
    async def test_create_revision_invalid_int_constraint(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test create Revision API with invalid int data.
        """
        # arrange
        await create_test_form(f"{self.data_dir}/form-create.json", session)
        # create test permissions
        set_id: int = await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.ADMIN)

        # create submission
        builder = SubmissionBuilder(
            cache=redis_client, session=session, static_cache=static_cache
        )
        submission = await builder.generate(
            nz_id=NZ_ID,
            table_view_id=1,
            permissions_set_id=set_id,
            tpl_file="form-create-sub.json",
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
        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}",
            json={
                "restatements": [
                    {
                        "path": "reporting_year",
                        "reason": "example",
                        "value": 2300,
                    }
                ],
            },
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        j_resp = response.json()
        assert j_resp["reason"] == "Constraints validation error."
        assert j_resp["loc"] == "reporting_year"
        assert j_resp["value"] == 2300
        assert "constraint_action" in j_resp

    @pytest.mark.asyncio
    async def test_create_revision_invalid_date_constraint_min(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test create Revision API with invalid date: below min.
        """
        # arrange
        await create_test_form(f"{self.data_dir}/form-create.json", session)
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
            tpl_file="form-create-sub.json",
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
        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}",
            json={
                "restatements": [
                    {
                        "path": "date_end_reporting_year",
                        "reason": "example",
                        "value": "1995-09-05T00:00:00.000Z",
                    }
                ],
            },
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        j_resp = response.json()
        assert j_resp["reason"] == "Constraints validation error."
        assert j_resp["loc"] == "date_end_reporting_year"
        assert j_resp["value"] == "1995-09-05T00:00:00.000Z"
        assert "constraint_action" in j_resp

    @pytest.mark.asyncio
    async def test_create_revision_invalid_date_constraint_max(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test create Revision API with invalid date: above max.
        """
        # arrange
        await create_test_form(f"{self.data_dir}/form-create.json", session)
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
            tpl_file="form-create-sub.json",
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
        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}",
            json={
                "restatements": [
                    {
                        "path": "date_end_reporting_year",
                        "reason": "example",
                        "value": "2300-05-06T00:00:00.000Z",
                    }
                ],
            },
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        j_resp = response.json()
        assert j_resp["reason"] == "Constraints validation error."
        assert j_resp["loc"] == "date_end_reporting_year"
        assert j_resp["value"] == "2300-05-06T00:00:00.000Z"
        assert "constraint_action" in j_resp

    @pytest.mark.asyncio
    async def test_create_revision_invalid_date_constraint_format(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test create Revision API with invalid date format.
        """
        # arrange
        await create_test_form(f"{self.data_dir}/form-create.json", session)
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
            tpl_file="form-create-sub.json",
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
        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}",
            json={
                "restatements": [
                    {
                        "path": "date_end_reporting_year",
                        "reason": "example",
                        "value": "27-06-2023T00:00:00.000Z",
                    }
                ],
            },
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        j_resp = response.json()
        assert (
            j_resp["detail"]["date_end_reporting_year"]
            == "datetime 27-06-2023T00:00:00.000Z is not a valid isoformat"
            " string"
        )

    @pytest.mark.asyncio
    async def test_create_revision_not_checked_out_fails(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test create Revision API on a non-checked out revision. Raises
        http error 403.
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
        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}",
            json={
                "restatements": [
                    {
                        "path": "org_boundary_approach",
                        "reason": "Fixed wrong method",
                        "value": 103,
                    },
                    {
                        "path": "scope_1_methodology",
                        "reason": "Added new methodologies",
                        "value": [101, 104],
                    },
                ]
            },
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_403_FORBIDDEN
        j_resp = response.json()
        assert (
            j_resp["detail"]["submission_name"]
            == "Could not edit the current submission: it is not checked out."
        )

    @pytest.mark.asyncio
    async def test_create_revision_co_by_other_user_fails(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test create Revision API on a revision checked out by another
        user. Raises http error 401.
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
        await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/edit",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # get access token for a different user
        new_access_token = await self.create_more_users(
            client=client,
            session=session,
            user_name="testuser_2",
            user_pass="testpass2",
        )
        # add permissions for new user
        session.add(
            Permission(
                set_id=1,
                user_id=2,
                grant=True,
                list=True,
                read=True,
                write=True,
            )
        )
        await self.add_role_to_user(
            session, AuthRole.DATA_PUBLISHER, "testuser_2"
        )
        await session.commit()
        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}",
            json={
                "restatements": [
                    {
                        "path": "org_boundary_approach",
                        "reason": "Fixed wrong method",
                        "value": 103,
                    },
                    {
                        "path": "scope_1_methodology",
                        "reason": "Added new methodologies",
                        "value": [101, 104],
                    },
                ]
            },
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {new_access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        j_resp = response.json()
        assert (
            j_resp["detail"]["global"]
            == "Could not edit the current submission: it has been checked out"
            " from another user."
        )


class TestSetEditMode(AuthTest):
    """
    Test set edit mode for latest submission revision.
    """

    data_dir: str = f"{settings.BASE_DIR}/../tests/data"

    @pytest.mark.asyncio
    async def test_set_edit_mode(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test set edit mode for latest submission revision.
        """
        # arrange
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # create submission
        builder = SubmissionBuilder(
            cache=redis_client, session=session, static_cache=static_cache
        )
        submission = await builder.generate(
            nz_id=NZ_ID,
            table_view_id=1,
            tpl_file=SUBMISSION_SCHEMA_FILE_NAME,
            no_change=True,
        )
        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/edit",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert j_resp["checked_out"]

    @pytest.mark.asyncio
    async def test_set_edit_mode_co_force_false_raises(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Tests setting edit mode for an already checked out submission,
        with force parameter unset. Raises http error 403.
        """
        # arrange
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # create submission
        builder = SubmissionBuilder(
            cache=redis_client, session=session, static_cache=static_cache
        )
        submission = await builder.generate(
            nz_id=NZ_ID,
            table_view_id=1,
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
        # try to check out again (shall fail)
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/edit",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_403_FORBIDDEN
        j_resp = response.json()
        assert (
            j_resp["detail"]["submission_name"]
            == "Could not perform request: submission is already checked out."
        )

    @pytest.mark.asyncio
    async def test_set_edit_mode_co_force_true_raises(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Tests setting edit mode for an already checked out submission,
        with force parameter True, but not enough rights on the
        requesting user. Raises http error 401.
        """
        # arrange
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # create submission
        builder = SubmissionBuilder(
            cache=redis_client, session=session, static_cache=static_cache
        )
        submission = await builder.generate(
            nz_id=1000,
            table_view_id=1,
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
        # try to check out again (shall fail)
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/edit",
            params={"force": True},
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        j_resp = response.json()
        assert (
            j_resp["detail"]["global"]
            == "Not enough rights to check out the current (already checked"
            " out)"
            " submission."
        )

    @pytest.mark.asyncio
    async def test_set_edit_mode_co_force_true_success(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Tests setting edit mode for an already checked out submission,
        with force parameter True, enough rights on the requesting user.
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
        # try to check out again (shall succeed)
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/edit",
            params={"force": True},
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert j_resp["checked_out"]

    @pytest.mark.asyncio
    async def test_set_edit_mode_submission_not_exist(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
    ):
        """
        Tests setting edit mode for a non-existing submission.
        Raises http error 404.
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        await static_cache.refresh_values()
        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/non_existing_submission/edit",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        j_resp = response.json()
        assert j_resp["detail"] == {
            "submission_name": "Submission object not found."
        }

    @pytest.mark.asyncio
    async def test_set_edit_mode_insufficient_rights(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Tests setting edit mode for a submission with a user who has insufficient rights.
        Raises http error 403.
        """
        # arrange
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await static_cache.refresh_values()
        # create user
        token = await self.create_more_users(
            client=client,
            session=session,
            user_name="test2",
            user_pass="testpass2",
        )
        await self.add_role_to_user(
            session=session,
            role_name=AuthRole.DATA_EXPLORER,
            user_name="test2",
        )
        # create submission
        builder = SubmissionBuilder(
            cache=redis_client, session=session, static_cache=static_cache
        )
        submission = await builder.generate(
            nz_id=NZ_ID,
            table_view_id=1,
            tpl_file=SUBMISSION_SCHEMA_FILE_NAME,
            no_change=True,
        )
        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/edit",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_403_FORBIDDEN
        j_resp = response.json()
        assert j_resp["detail"] == {
            "global": "Access denied: insufficient permissions."
        }


class TestClearEditMode(AuthTest):
    """
    Tests for clearing edit mode for a submission.
    """

    # CLEAR EDIT MODE
    data_dir: str = f"{settings.BASE_DIR}/../tests/data"

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
            nz_id=NZ_ID,
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
        assert not j_resp["checked_out"]

    @pytest.mark.asyncio
    async def test_clear_edit_mode_different_user_fails(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test clear edit mode on a submission checked out by another user.
        """
        # arrange
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # create submission
        builder = SubmissionBuilder(
            cache=redis_client, session=session, static_cache=static_cache
        )
        submission = await builder.generate(
            nz_id=NZ_ID,
            table_view_id=1,
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
        # get access token for a different user
        new_access_token = await self.create_more_users(
            client=client,
            session=session,
            user_name="testuser_2",
            user_pass="testpass2",
        )
        await self.add_role_to_user(
            session, AuthRole.DATA_PUBLISHER, "testuser_2"
        )
        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/edit/clear",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {new_access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_403_FORBIDDEN
        j_resp = response.json()
        assert (
            j_resp["detail"]["global"]
            == "Could not clear edit mode for current submission: it has been"
            " checked out by another user."
        )

    @pytest.mark.asyncio
    async def test_clear_edit_mode_not_enough_rights_fails(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        """
        Test clear edit mode for a checked out submission by a user
        without enough rights to clear the checked out state.
        """
        # arrange
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # create submission
        builder = SubmissionBuilder(
            cache=redis_client, session=session, static_cache=static_cache
        )
        submission = await builder.generate(
            nz_id=NZ_ID,
            table_view_id=1,
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
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        j_resp = response.json()
        assert (
            j_resp["detail"]["global"]
            == "Could not clear edit mode for current submission: not enough"
            " rights."
        )

    @pytest.mark.asyncio
    async def test_clear_edit_mode_non_existent_submission_fails(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
    ):
        """
        Test clear edit mode for a non-existent submission.
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        await static_cache.refresh_values()
        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/nonexistent/edit/clear",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert

        assert response.status_code == status.HTTP_404_NOT_FOUND
        j_resp = response.json()
        assert j_resp["detail"] == {
            "submission_name": "Submission object not found."
        }


class TestSubmissionRollback(AuthTest):
    """
    Test rollback submission API.
    """

    data_dir: Path = settings.BASE_DIR.parent / "tests" / "data"

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
            nz_id=NZ_ID,
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
        assert j_resp["name"].startswith("NZDPU-nzdpu_form")
        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/rollback",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_404_NOT_FOUND, response.text
        j_resp = response.json()
        assert j_resp["detail"] == {
            "global": "Previous active Submission object not found."
        }

    @pytest.mark.asyncio
    async def test_rollback_submission_no_active(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
    ):
        """_summary_

        Args:
            client (AsyncClient): _description_
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        await static_cache.refresh_values()
        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/nonexistent/rollback",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert

        assert response.status_code == status.HTTP_404_NOT_FOUND
        j_resp = response.json()
        assert j_resp["detail"] == {
            "global": "There is no active Submission object found."
        }

    @pytest.mark.asyncio
    async def test_rollback_submission_only_one_active(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        # arrange
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
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
        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/rollback",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        j_resp = response.json()
        assert j_resp["detail"] == {
            "global": "Previous active Submission object not found."
        }

    @pytest.mark.asyncio
    async def test_create_revision_with_updated_checked_out(
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
            url=f"{BASE_ENDPOINT}/{submission.name}/edit",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        edit = response.json()
        assert edit["id"] == 1
        assert edit["user_id"] == 1
        assert edit["checked_out"] is True
        # create revision
        response_revision = await client.post(
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
        # assert
        assert (
            response_revision.status_code == status.HTTP_200_OK
        ), response.text
        j_resp = response_revision.json()
        assert j_resp["id"] == 2
        assert j_resp["submitted_by"] == 1
        assert j_resp["checked_out"]
        # check if last revision checked_out is now False
        response_last_revision = await client.get(
            url="submissions/1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response_last_revision.status_code == status.HTTP_200_OK
        j_resp = response_last_revision.json()
        assert j_resp["id"] == 1
        assert j_resp["user_id"] is None
        assert j_resp["submitted_by"] == 1
        assert j_resp["checked_out"] is False
        assert j_resp["checked_out_on"] is None

    @pytest.mark.asyncio
    async def test_rollback_submission_no_activated_submissions(
        self,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        static_cache: CoreMemoryCache,
    ):
        # arrange
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        set_id: int = await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        builder = SubmissionBuilder(
            cache=redis_client, session=session, static_cache=static_cache
        )
        submission = await builder.generate(
            nz_id=1000,
            table_view_id=1,
            permissions_set_id=set_id,
            tpl_file=SUBMISSION_SCHEMA_FILE_NAME,
        )
        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/rollback",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        j_resp = response.json()
        assert j_resp["detail"] == {
            "global": "Previous active Submission object not found."
        }

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
        form_schema_file = self.data_dir / SCHEMA_FILE_NAME
        await create_test_form(form_schema_file, session)
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
        strip_none(submission.values)
        strip_none(draft["values"])

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


class TestSubmissionRevisionDelete(AuthTest):
    """
    Test rollback submission API.
    """

    data_dir: Path = settings.BASE_DIR.parent / "tests" / "data"

    @pytest.mark.asyncio
    async def test_delete_revision(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
        redis_client,
        submission_payload_revision,
    ):
        """
        Test delete a revision and all related records API
        """
        # Arrange
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        # Create test permissions
        set_id: int = await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # Create submission
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
        # Set it checked out
        await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/edit",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # Create revision
        await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}",
            json=submission_payload_revision,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # Act: Delete the revision
        response = await client.delete(
            url=f"{BASE_ENDPOINT}/{submission.name}/2",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # Assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert j_resp["success"] is True
