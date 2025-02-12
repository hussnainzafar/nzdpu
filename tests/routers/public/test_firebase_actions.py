"""
Tests for firebase action handlers.
"""

from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from fastapi import status
from firebase_admin.auth import Client
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    initialize_firebase_auth_client,
    initialize_firebase_rest_api_client,
)
from app.schemas.user import UserCreate
from app.service.firebase_rest_api_client.models import FirebaseRequestTypeEnum

BASE_ENDPOINT = "/public/firebase-action"

firebase = pytest.mark.skipif("not config.getoption('firebase')")
pb = initialize_firebase_rest_api_client()


@firebase
@pytest.mark.firebase
@pytest.mark.asyncio
async def test_confirm_password_reset(
    client: AsyncClient, session: AsyncSession
):
    # arrange
    user_email = "testuser@public.com"
    # create user
    user = UserCreate(
        name="test_user_public",
        first_name="Anonymous",
        last_name="User",
        email=user_email,
        api_key=str(uuid4()),
        password="T3stpassw0rd",
    )  # type: ignore
    new_user = await client.post(
        url="/public/users/register",
        json=user.dict(),
    )
    assert new_user.status_code == status.HTTP_200_OK, new_user.text

    # generate password reset link to get oobCode
    _fb: Client
    with initialize_firebase_auth_client() as _fb:
        link = _fb.generate_password_reset_link(email=user_email)
    # get oobCode from generated link
    qs = urlparse(link).query
    oob_code = parse_qs(qs)["oobCode"][0]

    # act
    response = await client.post(
        url=f"{BASE_ENDPOINT}/confirm-password-reset",
        json={"oobCode": oob_code, "password": "Testp4ssword"},
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    # try performing sign in to check password has changed
    sign_in = pb.sign_in_with_email_and_password(
        email=user_email, password="Testp4ssword"
    )
    assert sign_in.email == user_email
    assert sign_in.id_token


@firebase
@pytest.mark.firebase
@pytest.mark.asyncio
async def test_confirm_email_verification(
    client: AsyncClient, session: AsyncSession
):
    # arrange
    user_email = "testuser@public.com"
    # create user
    user = UserCreate(
        name="test_user_public",
        first_name="Anonymous",
        last_name="User",
        email=user_email,
        api_key=str(uuid4()),
        password="T3stpassw0rd",
    )  # type: ignore
    new_user = await client.post(
        url="/public/users/register",
        json=user.dict(),
    )
    assert new_user.status_code == status.HTTP_200_OK, new_user.text

    # generate email verification link to get oobCode
    _fb: Client
    with initialize_firebase_auth_client() as _fb:
        link = _fb.generate_email_verification_link(email=user_email)
    # get oobCode from generated link
    qs = urlparse(link).query
    oob_code = parse_qs(qs)["oobCode"][0]

    # act
    response = await client.post(
        url=f"{BASE_ENDPOINT}/confirm-email-verification",
        json={"oobCode": oob_code},
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    # get user from firebase to check email_verified value changed
    _fb: Client
    with initialize_firebase_auth_client() as _fb:
        fb_user = _fb.get_user_by_email(email=user_email)
    assert fb_user.email_verified


@firebase
@pytest.mark.firebase
@pytest.mark.asyncio
async def test_verify_password_reset_code(
    client: AsyncClient, session: AsyncSession
):
    # Create user.
    user_email = "reset_pass_user@public.com"
    user = UserCreate(
        name="reset_pass_user",
        first_name="Anonymous",
        last_name="User",
        email=user_email,
        api_key=str(uuid4()),
        password="T3stpassw0rd",
    )  # type: ignore
    new_user = await client.post(
        url="/public/users/register",
        json=user.dict(),
    )
    assert new_user.status_code == status.HTTP_200_OK, new_user.text

    # Generate password reset link to get the oobCode.
    _fb: Client
    with initialize_firebase_auth_client() as _fb:
        link = _fb.generate_password_reset_link(email=user_email)
    # get oobCode from generated link
    qs = urlparse(link).query
    oob_code = parse_qs(qs)["oobCode"][0]

    # Test with malformed code.
    response = await client.post(
        url=f"{BASE_ENDPOINT}/verify-password-reset-code",
        json={"oobCode": "malformed-oob-code"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST, response.text

    # Test with good oob code.
    response = await client.post(
        url=f"{BASE_ENDPOINT}/verify-password-reset-code",
        json={"oobCode": oob_code},
    )
    assert response.status_code == status.HTTP_200_OK, response.text

    # Check that response is as expected
    response = response.json()
    assert response["email"] == user_email
    assert response["requestType"] == FirebaseRequestTypeEnum.PASSWORD_RESET
