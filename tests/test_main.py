"""Test main package"""

import asyncio
from time import sleep

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings
from app.db.models import AuthRole, Group, User
from app.dependencies import (
    initialize_firebase_auth_client,
    initialize_firebase_rest_api_client,
)
from app.main import app
from app.service.firebase_rest_api_client import (
    FirebaseRESTAPIClientException,
)
from app.service.firebase_rest_api_client.client import (
    FirebaseRESTAPIClient,
)
from app.utils import encrypt_password


def mock_initialize_firebase_rest_api_client():
    client_fb = FirebaseRESTAPIClient(api_key="test")

    def test(refresh_token):
        raise FirebaseRESTAPIClientException(detail="test", status_code=400)

    client_fb.get_id_token_from_refresh_token = test
    return client_fb


firebase = pytest.mark.skipif(
    "not config.getoption('firebase')",
    reason="Use --firebase to perform test.",
)


async def verify_user_email(session: AsyncSession, user_id):
    stmt = select(User).where(User.id == user_id)
    db_user = await session.scalar(stmt)
    assert db_user
    # verify user email
    firebase_auth_client = initialize_firebase_auth_client()
    with firebase_auth_client as _fb:
        _fb.update_user(uid=db_user.external_user_id, email_verified=True)


class TestMain:
    """
    Unit tests for main APIs
    """

    user_name: str = "testuser"
    user_pass: str = "T3stpassw0rd"
    user_email: str = "test@mail.com"

    @pytest.mark.asyncio
    async def test_get_token(self, client: AsyncClient, session: AsyncSession):
        """
        Test "Get Token" API
        """
        # create test user
        encrypted_pwd = encrypt_password(self.user_pass)
        user = User(name=self.user_name, password=encrypted_pwd)
        session.add(user)
        await session.commit()

        # request a token for user
        response = await client.post(
            "/token",
            data={"username": self.user_name, "password": self.user_pass},
        )

        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert j_resp["access_token"]
        assert j_resp["refresh_token"]
        assert j_resp["token_type"] == "bearer"

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_get_token_firebase_email_not_verified(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test refresh token API for firebase users.
        """
        # arrange
        # create test user
        user = await client.post(
            url="/public/users/register",
            json={
                "name": self.user_name,
                "first_name": "test",
                "last_name": "user",
                "api_key": settings.fb.api_key,
                "email": self.user_email,
                "password": self.user_pass,
            },
        )
        assert user.status_code == status.HTTP_200_OK, user.text

        # request a token for user
        login = await client.post(
            "/token",
            data={"username": self.user_name, "password": self.user_pass},
        )
        assert login.status_code == 400, login.text
        j_resp = login.json()
        assert (
            j_resp["detail"]["email"]
            == "You need to verify your email before being able to log in."
            " Please check your associated email for the verification link."
        )

    @pytest.mark.asyncio
    async def test_refresh_token_local(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test refresh token API for local users.
        """
        # arrange
        # create test user
        encrypted_pwd = encrypt_password(self.user_pass)
        user = User(name=self.user_name, password=encrypted_pwd)
        group = Group(name=AuthRole.DATA_EXPLORER)
        session.add(group)
        user.groups.append(group)
        session.add(user)
        await session.commit()

        # request a token for user
        login = await client.post(
            "/token",
            data={"username": self.user_name, "password": self.user_pass},
        )

        assert login.status_code == 200, login.text
        j_resp = login.json()
        assert j_resp["access_token"]
        assert j_resp["refresh_token"]
        assert j_resp["token_type"] == "bearer"

        refresh_token = j_resp["refresh_token"]

        app.dependency_overrides[initialize_firebase_rest_api_client] = (
            mock_initialize_firebase_rest_api_client
        )

        # act
        refresh = await client.post(
            url="/token/refresh", json={"refresh_token": refresh_token}
        )

        # assert
        assert refresh.status_code == status.HTTP_200_OK, refresh.text
        j_resp = refresh.json()
        assert j_resp["access_token"]
        assert j_resp["refresh_token"]
        assert j_resp["token_type"] == "bearer"

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_refresh_token_firebase(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test refresh token API for firebase users.
        """
        # arrange
        # create test user
        user = await client.post(
            url="/public/users/register",
            json={
                "name": self.user_name,
                "first_name": "test",
                "last_name": "user",
                "api_key": settings.fb.api_key,
                "email": self.user_email,
                "password": self.user_pass,
            },
        )
        assert user.status_code == status.HTTP_200_OK, user.text
        await verify_user_email(session=session, user_id=user.json()["id"])

        # request a token for user
        login = await client.post(
            "/token",
            data={"username": self.user_name, "password": self.user_pass},
        )
        assert login.status_code == 200, login.text
        j_resp = login.json()
        assert j_resp["access_token"]
        assert j_resp["refresh_token"]
        assert j_resp["token_type"] == "bearer"

        refresh_token = j_resp["refresh_token"]

        # act
        refresh = await client.post(
            url="/token/refresh", json={"refresh_token": refresh_token}
        )

        # assert
        assert refresh.status_code == status.HTTP_200_OK, refresh.text
        j_resp = refresh.json()
        assert j_resp["access_token"]
        assert j_resp["refresh_token"]
        assert j_resp["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_invalid_password_increment_attempts_local(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test invalid password increments login attempts for local users.
        """
        # arrange
        # create test user
        encrypted_pwd = encrypt_password(self.user_pass)
        user = User(name=self.user_name, password=encrypted_pwd)
        session.add(user)
        await session.commit()

        # act
        # request a token for user
        login = await client.post(
            "/token",
            data={"username": self.user_name, "password": "wrongpass"},
        )

        # assert
        assert login.status_code == 401, login.text
        j_resp = login.json()
        assert j_resp["detail"] == {
            "password": (
                "Incorrect email or password. Please try again or reset your"
                " password."
            )
        }

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_invalid_password_increment_attempts_firebase(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test invalid password increments login attempts for local users.
        """
        # arrange
        # create test user
        user = await client.post(
            url="/public/users/register",
            json={
                "name": self.user_name,
                "first_name": "test",
                "last_name": "user",
                "api_key": settings.fb.api_key,
                "email": self.user_email,
                "password": self.user_pass,
            },
        )
        assert user.status_code == status.HTTP_200_OK, user.text

        # act
        # request a token for user
        login = await client.post(
            "/token",
            data={"username": self.user_name, "password": "wrongpass"},
        )

        # assert
        assert login.status_code == 401, login.text
        j_resp = login.json()
        assert j_resp["detail"] == {
            "password": (
                "Incorrect email or password. Please try again or reset your"
                " password."
            )
        }

    @pytest.mark.asyncio
    async def test_invalid_password_increment_attempts_local_max_reached(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test invalid password increments login attempts for local users.
        """
        # arrange
        # create test user
        encrypted_pwd = encrypt_password(self.user_pass)
        user = User(name=self.user_name, password=encrypted_pwd)
        session.add(user)
        await session.commit()

        for _ in range(settings.application.password_max_login_attempts - 1):
            # request a token for user
            login = await client.post(
                "/token",
                data={"username": self.user_name, "password": "wrongpass"},
            )

            assert login.status_code == 401, login.text
            j_resp = login.json()
            assert j_resp["detail"] == {
                "password": (
                    "Incorrect email or password. Please try again or reset"
                    " your password."
                )
            }

        # act
        # last failing request
        login = await client.post(
            "/token",
            data={"username": self.user_name, "password": "wrongpass"},
        )

        # assert
        assert login.status_code == 401, login.text
        j_resp = login.json()
        assert j_resp["detail"]["password"] == (
            "Your account has been temporarily locked due to too many failed login attempts. "
            "Please try again later, or reset your password."
        )

    @pytest.mark.asyncio
    async def test_refresh_token_local_invalidates_token(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test refresh token API for local users.
        """
        # arrange
        # create test user
        encrypted_pwd = encrypt_password(self.user_pass)
        user = User(name=self.user_name, password=encrypted_pwd)
        session.add(user)
        await session.commit()

        # request a token for user
        login = await client.post(
            "/token",
            data={"username": self.user_name, "password": self.user_pass},
        )

        assert login.status_code == 200, login.text
        j_resp = login.json()
        assert j_resp["access_token"]
        assert j_resp["refresh_token"]
        assert j_resp["token_type"] == "bearer"

        old_token = j_resp["access_token"]
        refresh_token = j_resp["refresh_token"]

        app.dependency_overrides[initialize_firebase_rest_api_client] = (
            mock_initialize_firebase_rest_api_client
        )

        sleep(1)  # wait to invalidate token
        refresh = await client.post(
            url="/token/refresh", json={"refresh_token": refresh_token}
        )

        assert refresh.status_code == status.HTTP_200_OK, refresh.text
        assert j_resp["access_token"]
        assert j_resp["refresh_token"]
        assert j_resp["token_type"] == "bearer"

        # act
        # try to call an authenticated API to check the token is invalid
        response = await client.get(
            url="/authorization/permissions/users/1",
            headers={"Authorization": f"Bearer {old_token}"},
        )

        # assert
        assert (
            response.status_code == status.HTTP_401_UNAUTHORIZED
        ), response.text
        j_resp = response.json()
        assert j_resp["detail"] == {"token": "Invalid token"}

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_refresh_token_firebase_invalidates_token(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test refresh token API for firebase users.
        """
        # arrange
        # create test user
        user = await client.post(
            url="/public/users/register",
            json={
                "name": self.user_name,
                "first_name": "test",
                "last_name": "user",
                "api_key": settings.fb.api_key,
                "email": self.user_email,
                "password": self.user_pass,
            },
        )
        assert user.status_code == status.HTTP_200_OK, user.text
        await verify_user_email(session=session, user_id=user.json()["id"])

        # request a token for user
        login = await client.post(
            "/token",
            data={"username": self.user_name, "password": self.user_pass},
        )
        assert login.status_code == 200, login.text
        j_resp = login.json()
        assert j_resp["access_token"]
        assert j_resp["refresh_token"]
        assert j_resp["token_type"] == "bearer"

        old_token = j_resp["access_token"]
        refresh_token = j_resp["refresh_token"]

        await asyncio.sleep(1)  # wait to invalidate token
        refresh = await client.post(
            url="/token/refresh", json={"refresh_token": refresh_token}
        )

        assert refresh.status_code == status.HTTP_200_OK, refresh.text
        j_resp = refresh.json()
        assert j_resp["access_token"]
        assert j_resp["refresh_token"]
        assert j_resp["token_type"] == "bearer"

        # act
        # try to call an authenticated API to check the token is invalid
        response = await client.get(
            url="/files/vaults",
            headers={"Authorization": f"Bearer {old_token}"},
        )

        # assert
        assert (
            response.status_code == status.HTTP_401_UNAUTHORIZED
        ), response.text
        j_resp = response.json()
        assert j_resp["detail"] == {"token": "Invalid token"}

    @pytest.mark.asyncio
    async def test_system_specs_endpoint_with_env_api_key(
        self, client: AsyncClient, session: AsyncSession
    ):
        resp = await client.get(
            url="/system/api/specs",
            headers={"X-Api-Key": settings.application.system_api_key},
        )
        spec = resp.json()
        assert spec != {"detail": "Not authenticated"}
        assert "openapi" in spec

    @pytest.mark.asyncio
    async def test_fapi_default_docs_endpoints_disabled(
        self, client: AsyncClient, session: AsyncSession
    ):
        resp_swagger = await client.get("/docs")
        resp_redoc = await client.get("/redoc")
        assert resp_swagger.status_code == status.HTTP_401_UNAUTHORIZED
        assert resp_swagger.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_openapi_spec_user_create_schema_has_only_one_required_password_attribute(
        self, client: AsyncClient, session: AsyncSession
    ):
        resp = await client.get(
            url="/system/api/specs",
            headers={"X-Api-Key": settings.application.system_api_key},
        )
        resp_json = resp.json()
        required = resp_json["components"]["schemas"]["UserCreate"]["required"]
        assert "password" in required
        assert len(set(required)) == len(required)
