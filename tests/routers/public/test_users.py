"""User endpoint tests for public API."""

from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient, delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.settings as settings
from app.db.models import User
from app.schemas.user import AuthMode, OrganizationTypes, UserCreate

BASE_ENDPOINT = "/public/users"

firebase = pytest.mark.skipif("not config.getoption('firebase')")

# pylint: disable = unused-argument


@firebase
@pytest.mark.asyncio
@pytest.mark.firebase
async def test_create_user(client: AsyncClient, session: AsyncSession):
    """
    Test create user API
    """
    # act
    response = await client.post(
        url=f"{BASE_ENDPOINT}/register",
        json={
            "name": "test_user_public",
            "first_name": "Anonymous",
            "last_name": "User",
            "email": "testuser@public.com",
            "api_key": str(uuid4()),
            "password": "T3stpassw0rd",
            "organization_type": OrganizationTypes.FINANCIAL_INSTITUTION,
        },
        headers={
            "accept": "application/json",
        },
    )
    # assert
    assert response.status_code == status.HTTP_200_OK, response.text
    j_resp = response.json()
    assert j_resp["id"] == 1
    db_user = await session.scalar(select(User).where(User.id == j_resp["id"]))
    assert db_user
    assert db_user.organization_type == OrganizationTypes.FINANCIAL_INSTITUTION


@pytest.mark.firebase
@firebase
@pytest.mark.asyncio
async def test_send_email_verification(
    client: AsyncClient, session: AsyncSession
):
    """
    Test send email verification
    """

    # arrange
    user_email = "testuser@public.com"
    # create user
    user = User(
        name="test_user_public",
        first_name="Anonymous",
        last_name="User",
        email=user_email,
        api_key=str(uuid4()),
        password="T3stpassw0rd",
        auth_mode=AuthMode.FIREBASE,
    )  # type: ignore
    session.add(user)
    await session.flush()

    # act
    response = await client.post(
        url=f"{BASE_ENDPOINT}/send-email-verification",
        json={"email": user_email, "password": f"pass{uuid4()}"},
        headers={"accept": "application/json"},
    )
    # assert
    assert response.status_code == status.HTTP_404_NOT_FOUND, response.text
    j_resp = response.json()
    assert j_resp["detail"] == {
        "email": (
            "There is no user record corresponding to this identifier."
            " The user may have been deleted."
        )
    }


@pytest.mark.asyncio
async def test_organization_check_fails(
    client: AsyncClient, session: AsyncSession
):
    """
    Test create user API with invalid user data
    """
    response = await client.post(
        url=f"{BASE_ENDPOINT}/register",
        json={
            "name": "",
            "first_name": "",
            "last_name": "",
            "email": None,
            "api_key": str(uuid4()),
            "password": "T3stpassw0rd",
            "organization_type": "myorgtype",
        },
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@firebase
@pytest.mark.firebase
@pytest.mark.asyncio
async def test_reset_password(client: AsyncClient, session: AsyncSession):
    # arrange
    # create firebase user
    user_create_payload = UserCreate(
        name="fb_user",
        email="test@user.com",
        first_name="firebase",
        last_name="user",
        api_key="apikey",
        password="T3stpassw0rd",
    )  # type: ignore
    user_create = await client.post(
        url=f"{BASE_ENDPOINT}/register",
        json=user_create_payload.model_dump(),
    )
    assert user_create.status_code == status.HTTP_200_OK, user_create.text

    # act
    response = await client.post(
        url=f"{BASE_ENDPOINT}/reset-password",
        params={"email": "test@user.com"},
    )

    # assert
    assert response.status_code == status.HTTP_200_OK, response.text


@pytest.mark.asyncio
async def test_reset_password_user_not_found(
    client: AsyncClient, session: AsyncSession
):
    # act
    response = await client.post(
        url=f"{BASE_ENDPOINT}/reset-password",
        params={"email": "not@found.com"},
    )

    # assert
    assert (
        response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    ), response.text


@firebase
@pytest.mark.firebase
@pytest.mark.asyncio
async def test_reset_password_firebase_email_not_found(
    client: AsyncClient, session: AsyncSession
):
    # arrange
    # create firebase user
    user_create_payload = UserCreate(
        name="fb_user",
        email="test@user.com",
        first_name="firebase",
        last_name="user",
        api_key="apikey",
        password="T3stpassw0rd",
    )  # type: ignore
    user_create = await client.post(
        url=f"{BASE_ENDPOINT}/register",
        json=user_create_payload.model_dump(),
    )
    assert user_create.status_code == status.HTTP_200_OK, user_create.text

    # delete firebase user list
    project_id = settings.gcp.project
    delete(
        url=f"http://localhost:9099/emulator/v1/projects/{project_id}/accounts"
    )

    # act
    response = await client.post(
        url=f"{BASE_ENDPOINT}/reset-password",
        params={"email": "test@user.com"},
    )

    # assert
    assert response.status_code == status.HTTP_404_NOT_FOUND, response.text
    j_resp = response.json()
    assert j_resp["detail"] == {
        "email": (
            "There is no user record corresponding to this identifier."
            " The user may have been deleted."
        )
    }
