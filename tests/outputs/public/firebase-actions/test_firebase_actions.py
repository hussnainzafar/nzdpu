"""
Tests for firebase action handlers.
"""

import pytest
from fastapi import status
from httpx import AsyncClient

from app.dependencies import (
    initialize_firebase_rest_api_client,
)

BASE_ENDPOINT = "/public/firebase-action"

firebase = pytest.mark.skipif("not config.getoption('firebase')")
pb = initialize_firebase_rest_api_client()


@firebase
@pytest.mark.firebase
@pytest.mark.asyncio
async def test_confirm_password_reset(client: AsyncClient):
    # act

    response = await client.post(
        url=f"{BASE_ENDPOINT}/confirm-password-reset",
        json={"oobCode": "fake-oobjcode", "password": "fakse-pass"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    j_resp = response.json()
    assert j_resp == {
        "detail": {
            "oobCode": "The action code is invalid. This can happen if the code is malformed, expired, or has already been used."
        }
    }


@firebase
@pytest.mark.firebase
@pytest.mark.asyncio
async def test_confirm_email_verification(
    client: AsyncClient,
):
    # act
    response = await client.post(
        url=f"{BASE_ENDPOINT}/confirm-email-verification",
        json={"oobCode": "test-oobcode"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    j_resp = response.json()
    assert j_resp == {
        "detail": {
            "oobCode": "The action code is invalid. This can happen if the code is malformed, expired, or has already been used."
        }
    }
