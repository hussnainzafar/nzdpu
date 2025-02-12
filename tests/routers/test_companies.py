"""
Unit tests for companies endpoint
"""

import json
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app import settings
from app.db.models import (
    AuthRole,
    Group,
    Organization,
    Permission,
    User,
)
from app.db.redis import RedisClient
from app.service.core.cache import CoreMemoryCache
from app.service.submission_builder import SubmissionBuilder
from app.utils import encrypt_password
from tests.constants import (
    SCHEMA_FILE_NAME,
    SUBMISSION_SCHEMA_FILE_NAME,
    SUBMISSION_SCHEMA_FULL_FILE_NAME,
)

from .utils import NZ_ID, create_test_form

BASE_ENDPOINT = "/coverage/companies"
data_dir: Path = settings.BASE_DIR.parent / "tests" / "data"


async def create_organization(
    session: AsyncSession,
    lei: str,
    legal_name: str,
    jurisdiction: str,
    nz_id: int,
) -> Organization:
    organization = Organization(
        lei=lei, legal_name=legal_name, jurisdiction=jurisdiction, nz_id=nz_id
    )
    session.add(organization)
    await session.flush([organization])

    return organization


async def create_group(session: AsyncSession, name: str) -> Group:
    group = Group(name=name)
    session.add(group)
    await session.flush([group])

    return group


async def create_user(
    session: AsyncSession,
    name: str,
    email: str,
    first_name: str,
    last_name: str,
    api_key: str,
    password: str,
    organization_id: int,
    groups: list,
) -> User:
    user = User(
        name=name,
        email=email,
        first_name=first_name,
        last_name=last_name,
        api_key=api_key,
        password=password,
        organization_id=organization_id,
        groups=groups,
    )
    session.add(user)
    await session.commit()

    return user


async def create_permissions(
    session: AsyncSession, set_id: int, group_id: int, user_id: int
) -> None:
    session.add_all(
        [
            Permission(
                set_id=set_id,
                group_id=group_id,
                grant=True,
                list=True,
                read=True,
                write=True,
            ),
            Permission(
                set_id=set_id,
                user_id=user_id,
                grant=True,
                list=True,
                read=True,
                write=False,
            ),
        ]
    )
    await session.commit()


async def log_in_user(client: AsyncClient) -> str:
    token_response = await client.post(
        url="/token", data={"username": "testuser", "password": "testpass"}
    )
    assert (
        token_response.status_code == status.HTTP_200_OK
    ), token_response.text

    return token_response.json()["access_token"]


async def set_up_db(
    session: AsyncSession,
    client: AsyncClient,
    organization_lei: str,
    organization_legal_name: str,
    organization_jurisdiction: str,
    group_name: str,
    user_name: str,
    user_password: str,
    user_email: str,
    user_first_name: str,
    user_last_name: str,
    user_api_key: str,
    permissions_set_id: int,
    form_file: str = SCHEMA_FILE_NAME,
) -> str:
    # create test organization
    organization = await create_organization(
        session=session,
        lei=organization_lei,
        legal_name=organization_legal_name,
        jurisdiction=organization_jurisdiction,
        nz_id=NZ_ID,
    )
    # create test group
    group = await create_group(session=session, name=group_name)

    # create user
    user = await create_user(
        session=session,
        name=user_name,
        email=user_email,
        first_name=user_first_name,
        last_name=user_last_name,
        api_key=user_api_key,
        password=encrypt_password(user_password),
        organization_id=organization.id,
        groups=[group],
    )

    # create permissions for user and group
    await create_permissions(
        session=session,
        set_id=permissions_set_id,
        group_id=group.id,
        user_id=user.id,
    )

    await create_test_form(data_dir / form_file, session)

    # get user token
    return await log_in_user(client=client)


async def create_two_submissions(
    client: AsyncClient,
    static_cache: CoreMemoryCache,
    session: AsyncSession,
    submission_payload,
):
    """
    Creates two submissions of nzdpu_form for testing.

    1st submission `date_end_reporting_year`: "2020-01-01T00:00:00.000Z"
    1st submission `reporting_year`: 2015
    2nd submission `date_end_reporting_year`: "2021-01-01T00:00:00.000Z"
    2nd submission `reporting_year`: 2021
    """
    token = await set_up_db(
        session=session,
        client=client,
        organization_lei="000012345678",
        organization_legal_name="testorg",
        organization_jurisdiction="US-MA",
        group_name=AuthRole.DATA_PUBLISHER,
        user_name="testuser",
        user_password="testpass",
        user_email="test@user.com",
        user_first_name="test",
        user_last_name="user",
        user_api_key="apikey",
        permissions_set_id=1,
    )
    await static_cache.refresh_values()

    # create first submission
    submission_created = await client.post(
        url="/submissions",
        json=submission_payload,
        headers={
            "content-type": "application/json",
            "accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    assert (
        submission_created.status_code == status.HTTP_200_OK
    ), submission_created.text

    submission_payload["values"]["date_end_reporting_year"] = (
        "2021-01-01T00:00:00.000Z"
    )
    submission_payload["values"]["reporting_year"] = 2021

    # create second submission
    submission_created = await client.post(
        url="/submissions",
        json=submission_payload,
        headers={
            "content-type": "application/json",
            "accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    assert (
        submission_created.status_code == status.HTTP_200_OK
    ), submission_created.text

    await static_cache.refresh_values()


@pytest.fixture
def submission_payload():
    """
    Fixture for submission payload
    Returns
    -------
    submissions payload
    """

    with open(
        data_dir / SUBMISSION_SCHEMA_FULL_FILE_NAME, encoding="utf-8"
    ) as f:
        return {
            "nz_id": NZ_ID,
            "table_view_id": 1,
            "permissions_set_id": 1,
            "values": json.load(f),
        }


@pytest.mark.asyncio
async def test_historical_emissions_lei_only(
    client: AsyncClient,
    static_cache: CoreMemoryCache,
    session: AsyncSession,
    submission_payload,
):
    """
    Test historical emissions with only LEI specified.
    """

    # arrange
    await create_two_submissions(
        client, static_cache, session, submission_payload
    )

    # act
    response = await client.get(
        url=f"{BASE_ENDPOINT}/{NZ_ID}/history",
    )

    # assert
    assert response.status_code == status.HTTP_200_OK, response.text
    j_resp = response.json()
    assert j_resp["nz_id"] == NZ_ID
    assert j_resp["model"] is None
    assert j_resp["source"] is None
    assert len(j_resp["history"]) == 2
    assert j_resp["history"][0]["submission"]["units"]
    assert j_resp["history"][1]["submission"]["units"]
    # assert all keys are there
    assert not {"reporting_year", "submission"} - set(
        j_resp["history"][0].keys()
    )
    assert j_resp["history"][0]["reporting_year"] == 2015
    assert j_resp["history"][1]["reporting_year"] == 2021


@pytest.mark.asyncio
async def test_historical_emissions_lei_and_model(
    client: AsyncClient,
    session: AsyncSession,
    submission_payload,
    static_cache: CoreMemoryCache,
    redis_client: RedisClient,
):
    """
    Test historical emissions with LEI and model specified.
    """

    # arrange
    await create_two_submissions(
        client, static_cache, session, submission_payload
    )

    # act
    response = await client.get(
        url=f"{BASE_ENDPOINT}/{NZ_ID}/history", params={"model": "NZDPU Core"}
    )

    # assert
    assert response.status_code == status.HTTP_200_OK, response.text
    j_resp = response.json()
    assert j_resp["nz_id"] == NZ_ID
    assert j_resp["model"] == "NZDPU Core"
    assert j_resp["source"] is None
    assert len(j_resp["history"]) == 2
    assert j_resp["history"][0]["submission"]["units"]
    assert j_resp["history"][1]["submission"]["units"]
    # assert all keys are there
    assert not {"reporting_year", "submission"} - set(
        j_resp["history"][0].keys()
    )
    assert j_resp["history"][0]["reporting_year"] == 2015
    assert j_resp["history"][1]["reporting_year"] == 2021


@pytest.mark.asyncio
async def test_historical_emissions_lei_model_year_from(
    client: AsyncClient,
    session: AsyncSession,
    submission_payload,
    redis_client: RedisClient,
    static_cache: CoreMemoryCache,
):
    """
    Test historical emissions with LEI, model and year_from specified.
    """

    # arrange
    await create_two_submissions(
        client, static_cache, session, submission_payload
    )

    # act
    response = await client.get(
        url=f"{BASE_ENDPOINT}/{NZ_ID}/history",
        params={"model": "NZDPU Core", "year_from": 1998},
    )

    # assert
    assert response.status_code == status.HTTP_200_OK, response.text
    j_resp = response.json()
    assert j_resp["nz_id"] == NZ_ID
    assert j_resp["model"] == "NZDPU Core"
    assert j_resp["source"] is None
    assert len(j_resp["history"]) == 2
    assert j_resp["history"][0]["submission"]["units"]
    assert j_resp["history"][1]["submission"]["units"]
    # assert all keys are there
    assert not {"reporting_year", "submission"} - set(
        j_resp["history"][0].keys()
    )
    assert j_resp["history"][0]["reporting_year"] == 2015
    assert j_resp["history"][1]["reporting_year"] == 2021


@pytest.mark.asyncio
async def test_historical_emissions_lei_model_year_to(
    client: AsyncClient,
    session: AsyncSession,
    submission_payload,
    redis_client: RedisClient,
    static_cache: CoreMemoryCache,
):
    """
    Test historical emissions with LEI, model and year_to specified.
    """

    # arrange
    await create_two_submissions(
        client, static_cache, session, submission_payload
    )

    # act
    response = await client.get(
        url=f"{BASE_ENDPOINT}/{NZ_ID}/history",
        params={"model": "NZDPU Core", "year_to": 2022},
    )

    # assert
    assert response.status_code == status.HTTP_200_OK, response.text
    j_resp = response.json()
    assert j_resp["nz_id"] == NZ_ID
    assert j_resp["model"] == "NZDPU Core"
    assert j_resp["source"] is None
    assert len(j_resp["history"]) == 2
    assert j_resp["history"][0]["submission"]["units"]
    assert j_resp["history"][1]["submission"]["units"]
    # assert all keys are there
    assert not {"reporting_year", "submission"} - set(
        j_resp["history"][0].keys()
    )
    assert j_resp["history"][0]["reporting_year"] == 2015
    assert j_resp["history"][1]["reporting_year"] == 2021


@pytest.mark.asyncio
async def test_historical_emissions_lei_model_year_from_year_to(
    client: AsyncClient,
    session: AsyncSession,
    submission_payload,
    redis_client: RedisClient,
    static_cache: CoreMemoryCache,
):
    """
    Test historical emissions with LEI, model year_from and year_to
    specified.
    """

    # arrange
    await create_two_submissions(
        client, static_cache, session, submission_payload
    )

    # act
    response = await client.get(
        url=f"{BASE_ENDPOINT}/{NZ_ID}/history",
        params={"model": "NZDPU Core", "year_from": 1998, "year_to": 2023},
    )

    # assert
    assert response.status_code == status.HTTP_200_OK, response.text
    j_resp = response.json()
    assert j_resp["nz_id"] == NZ_ID
    assert j_resp["model"] == "NZDPU Core"
    assert j_resp["source"] is None
    assert len(j_resp["history"]) == 2
    assert j_resp["history"][0]["submission"]["units"]
    assert j_resp["history"][1]["submission"]["units"]
    # assert all keys are there
    assert not {"reporting_year", "submission"} - set(
        j_resp["history"][0].keys()
    )
    assert j_resp["history"][0]["reporting_year"] == 2015
    assert j_resp["history"][1]["reporting_year"] == 2021


@pytest.mark.asyncio
async def test_historical_emissions_wrong_lei_raise_404(
    client: AsyncClient,
    session: AsyncSession,
    submission_payload,
    redis_client: RedisClient,
    static_cache: CoreMemoryCache,
):
    """
    Test historical emissions with wrong LEI, raises 404
    """

    # arrange
    await create_two_submissions(
        client, static_cache, session, submission_payload
    )

    # act
    response = await client.get(
        url=f"{BASE_ENDPOINT}/9999999/history",
    )

    # assert
    assert response.status_code == status.HTTP_200_OK, response.text
    j_resp = response.json()
    assert j_resp == {
        "nz_id": 9999999,
        "model": None,
        "source": None,
        "history": [],
    }


@pytest.mark.asyncio
async def test_historical_emissions_wrong_model_no_reults(
    client: AsyncClient,
    session: AsyncSession,
    submission_payload,
    redis_client: RedisClient,
    static_cache: CoreMemoryCache,
):
    """
    Test historical emissions with LEI, wrong model returns no results.
    """

    # arrange
    await create_two_submissions(
        client, static_cache, session, submission_payload
    )

    # act
    response = await client.get(
        url=f"{BASE_ENDPOINT}/{NZ_ID}/history", params={"model": "99999"}
    )

    # assert
    assert response.status_code == status.HTTP_200_OK, response.text
    j_resp = response.json()
    assert j_resp["nz_id"] == NZ_ID
    assert j_resp["model"] == "99999"
    assert j_resp["source"] is None
    assert not j_resp["history"]


@pytest.mark.asyncio
async def test_historical_emissions_year_from_out_of_range_no_reults(
    client: AsyncClient,
    session: AsyncSession,
    submission_payload,
    redis_client: RedisClient,
    static_cache: CoreMemoryCache,
):
    """
    Test historical emissions with LEI, out of range year_from returns
    no results.
    """

    # arrange
    await create_two_submissions(
        client, static_cache, session, submission_payload
    )

    # act
    response = await client.get(
        url=f"{BASE_ENDPOINT}/{NZ_ID}/history",
        params={"year_from": 99999},
    )

    # assert
    assert response.status_code == status.HTTP_200_OK, response.text
    j_resp = response.json()
    assert j_resp["nz_id"] == NZ_ID
    assert j_resp["model"] is None
    assert j_resp["source"] is None
    assert not j_resp["history"]


@pytest.mark.asyncio
async def test_historical_emissions_year_to_out_of_range_no_reults(
    client: AsyncClient,
    session: AsyncSession,
    submission_payload,
    redis_client: RedisClient,
    static_cache: CoreMemoryCache,
):
    """
    Test historical emissions with LEI, out of range year_to returns
    no results.
    """

    # arrange
    await create_two_submissions(
        client, static_cache, session, submission_payload
    )

    # act
    response = await client.get(
        url=f"{BASE_ENDPOINT}/{NZ_ID}/history", params={"year_to": 1}
    )

    # assert
    assert response.status_code == status.HTTP_200_OK, response.text
    j_resp = response.json()
    assert j_resp["nz_id"] == NZ_ID
    assert j_resp["model"] is None
    assert j_resp["source"] is None
    assert not j_resp["history"]


@pytest.mark.asyncio
async def test_report_disclosure(
    client: AsyncClient,
    session: AsyncSession,
    submission_payload,
    redis_client: RedisClient,
    static_cache: CoreMemoryCache,
):
    """
    Test report disclosure
    """

    # arrange
    await create_two_submissions(
        client, static_cache, session, submission_payload
    )

    # act
    response = await client.get(
        url=f"{BASE_ENDPOINT}/{NZ_ID}/disclosures",
        params={
            "model": "NZDPU Core",
        },
    )

    # assert
    assert response.status_code == status.HTTP_200_OK, response.text
    j_resp = response.json()
    assert len(j_resp["items"]) == 2
    # assert all keys are there
    assert not {"year", "model", "last_updated", "submission_id"} - set(
        j_resp["items"][0].keys()
    )


@pytest.mark.asyncio
async def test_report_disclosure_with_start_limit_sort(
    client: AsyncClient,
    session: AsyncSession,
    submission_payload,
    redis_client: RedisClient,
    static_cache: CoreMemoryCache,
):
    """
    Test report disclosure with start, limit and sort parameters
    """

    # arrange
    await create_two_submissions(
        client, static_cache, session, submission_payload
    )

    # act
    response = await client.get(
        url=f"{BASE_ENDPOINT}/{NZ_ID}/disclosures",
        params={
            "model": "NZDPU Core",
            "start": 0,
            "limit": 1,
            "sort_by": "most_recent_year",
        },
    )

    # assert
    assert response.status_code == status.HTTP_200_OK, response.text
    j_resp = response.json()
    assert len(j_resp["items"]) == 1
    # assert all keys are there
    assert not {"year", "model", "last_updated", "submission_id"} - set(
        j_resp["items"][0].keys()
    )
    assert j_resp["items"][0]["year"] == 2021


@pytest.mark.asyncio
async def test_disclosure_details(
    client: AsyncClient,
    session: AsyncSession,
    submission_payload,
    redis_client: RedisClient,
    static_cache: CoreMemoryCache,
):
    """
    Test simplest disclosure-details call.
    """
    # arrange
    await create_two_submissions(
        client, static_cache, session, submission_payload
    )

    # act
    response = await client.get(
        url=f"{BASE_ENDPOINT}/{NZ_ID}/disclosure-details",
        params={"year": 2021},
    )

    # assert
    assert response.status_code == status.HTTP_200_OK, response.text
    j_resp = response.json()
    assert j_resp["values"]
    assert j_resp["units"]


@pytest.mark.asyncio
async def test_disclosure_details_with_model_source(
    client: AsyncClient,
    session: AsyncSession,
    submission_payload,
    redis_client: RedisClient,
    static_cache: CoreMemoryCache,
):
    """
    Test disclosure-details call with model and source parameters.
    """
    # arrange
    await create_two_submissions(
        client, static_cache, session, submission_payload
    )

    # act
    response = await client.get(
        url=f"{BASE_ENDPOINT}/{NZ_ID}/disclosure-details",
        params={
            "year": 2021,
            "model": "NZDPU Core",
            "source": "Vehicle Emissions",
        },
    )

    # assert
    assert response.status_code == status.HTTP_200_OK, response.text
    j_resp = response.json()
    assert j_resp["values"]
    assert j_resp["units"]


@pytest.mark.asyncio
async def test_disclosure_details_no_active_submissions_results_raise_404(
    client: AsyncClient,
    session: AsyncSession,
    submission_payload,
    redis_client: RedisClient,
    static_cache: CoreMemoryCache,
):
    """
    Test disclosure-details call with invalid year raises 404 not found.
    """
    # arrange
    await create_two_submissions(
        client, static_cache, session, submission_payload
    )

    # act
    response = await client.get(
        url=f"{BASE_ENDPOINT}/{NZ_ID}/disclosure-details",
        params={"year": 9999},
    )

    # assert
    assert response.status_code == status.HTTP_404_NOT_FOUND, response.text
    j_resp = response.json()
    assert j_resp["detail"] == {
        "submission": "No active submission found for the given parameters."
    }


@pytest.mark.asyncio
async def test_restated_fields_by_year(
    client: AsyncClient,
    session: AsyncSession,
    redis_client: RedisClient,
    static_cache: CoreMemoryCache,
):
    """
    Test /{nz_id}/disclosure-details/restated-fields endpoint.
    """

    # arrange
    permissions_set_id: int = 1
    organization_lei = "000012345678"
    token = await set_up_db(
        session=session,
        client=client,
        organization_lei=organization_lei,
        organization_legal_name="testorg",
        organization_jurisdiction="US-MA",
        group_name=AuthRole.DATA_PUBLISHER,
        user_name="testuser",
        user_password="testpass",
        user_email="test@user.com",
        user_first_name="test",
        user_last_name="user",
        user_api_key="apikey",
        permissions_set_id=permissions_set_id,
        form_file=SCHEMA_FILE_NAME,
    )
    # create submission
    builder = SubmissionBuilder(
        cache=redis_client, session=session, static_cache=static_cache
    )
    submission = await builder.generate(
        nz_id=NZ_ID,
        table_view_id=1,
        permissions_set_id=permissions_set_id,
        tpl_file=SUBMISSION_SCHEMA_FILE_NAME,
        no_change=True,
    )
    await static_cache.refresh_values()
    # set it checked out
    response = await client.post(
        url=f"/submissions/revisions/{submission.name}/edit",
        headers={
            "content-type": "application/json",
            "accept": "application/json",
            "Authorization": f"Bearer {token}",
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
            "Authorization": f"Bearer {token}",
        },
    )
    assert response.status_code == status.HTTP_200_OK, response.text

    # act
    response = await client.get(
        url=f"{BASE_ENDPOINT}/{NZ_ID}/disclosure-details/restated-fields",
        params={"year": 2020},
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    j_resp = response.json()
    assert j_resp["name"]
    assert j_resp["fields"] == [
        "s1_emissions_exclusion_dict.{::0}.s1_emissions_exclusion_perc"
    ]


@pytest.mark.asyncio
async def test_get_targets_progress_success(
    client: AsyncClient,
    session: AsyncSession,
    submission_payload,
    redis_client: RedisClient,
    static_cache: CoreMemoryCache,
):
    """
    Test /{nz_id}/targets/progress endpoint.
    """
    # arrange
    await create_two_submissions(
        client, static_cache, session, submission_payload
    )

    # Act: Make the GET request to the endpoint
    response = await client.get(
        f"{BASE_ENDPOINT}/{NZ_ID}/targets/progress",
        params={"model": "NZDPU Core"},
    )

    # Assert: Check the response and its content
    assert response.status_code == status.HTTP_200_OK, response.text
    data = response.json()
    assert "targets_progress" in data
    assert isinstance(data["targets_progress"], list)
    assert data["targets_progress"][0]["data_source"] is not None


@pytest.mark.asyncio
async def test_get_targets_progress_not_found(
    client: AsyncClient,
    static_cache: CoreMemoryCache,
    session: AsyncSession,
    redis_client: RedisClient,
):
    """
    Test case for an error response (e.g., 422 unprocessable entity)

    Test /{nz_id}/targets/progress endpoint.
    """
    # Arrange: No need to create database records in this case

    # Act: Make the GET request to the endpoint
    await static_cache.refresh_values()
    response = await client.get(
        f"{BASE_ENDPOINT}/87923748/targets/progress",
        params={
            "model": "NZDPU Core",
            "year_start": 2019,
            "year_end": 2020,
            "data_sources": "company_reported",
        },
    )

    # Assert: Check for a 422 Not processable response
    assert (
        response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    ), response.text


@pytest.mark.asyncio
async def test_get_targets(
    client: AsyncClient,
    session: AsyncSession,
    submission_payload,
    redis_client: RedisClient,
    static_cache: CoreMemoryCache,
):
    """
    Test /{nz_id}/targets endpoint.
    """
    # arrange
    await create_two_submissions(
        client, static_cache, session, submission_payload
    )
    tgt_id = "abs_id_1"
    active = True
    # Act: Make the GET request to the endpoint
    response = await client.get(
        f"{BASE_ENDPOINT}/{NZ_ID}/targets", params={"active": active}
    )
    # Assert: Check the response and its content
    assert response.status_code == status.HTTP_200_OK, response.text
    data = response.json()
    assert isinstance(data, dict)
    assert len(data.get("targets")) == 1
