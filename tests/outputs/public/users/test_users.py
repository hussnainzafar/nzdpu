"""User endpoint tests for public API."""

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.user import UserCreate

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
            "name": "string",
            "first_name": "string",
            "last_name": "string",
            "api_key": "string",
            "email": "user@example.com",
            "password": "string",
            "groups": [],
            "organization_type": "Financial Institution",
        },
        headers={
            "accept": "application/json",
        },
    )
    # assert
    assert response.status_code == status.HTTP_400_BAD_REQUEST, response.text
    j_resp = response.json()
    assert j_resp == {
        "detail": {"password": "Password must be at least 12 characters long."}
    }


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
        params={"email": "test%40nzdpu.com"},
    )

    # assert
    assert (
        response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    ), response.text
    j_resp = response.json()
    assert j_resp == {
        "detail": {
            "email": "If a matching account was found, an email was sent to test%40nzdpu.com to allow you to reset your password. If you do not receive the email, please check your Spam folder, click below to resend the link, or consider {{REGISTER_LINK}}"
        }
    }


@pytest.mark.asyncio
async def test_send_email_verification(
    client: AsyncClient, session: AsyncSession
):
    """
    Test send email verification
    """

    # act
    response = await client.post(
        url=f"{BASE_ENDPOINT}/send-email-verification",
        json={
            "username": "testuser",
            "email": "test@nzdpu.com",
            "password": "testpass123",
        },
    )
    # assert'
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    j_resp = response.json()
    assert j_resp == {
        "detail": {
            "email": "Incorrect email or password. Please try again or reset your password."
        }
    }
