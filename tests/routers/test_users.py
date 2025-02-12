"""Unit tests for users router"""

import csv
import io
from datetime import datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException, status
from httpx import AsyncClient
from httpx import delete as httpxdelete
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import app.settings as settings
from app.db.models import AuthMode, AuthRole, Group, Permission, Tracking, User
from app.dependencies import initialize_firebase_auth_client
from app.routers.utils import is_valid_password
from app.schemas.user import OrganizationTypes, UserCreate
from tests.routers.auth_test import AuthTest

from ..test_main import verify_user_email

BASE_ENDPOINT = "/authorization/permissions/users"

firebase = pytest.mark.skipif(
    "not config.getoption('firebase')",
    reason="Use --firebase to perform test.",
)


class TestUsersList(AuthTest):
    """
    Unit tests for users APIs
    """

    # LIST USERS
    @pytest.mark.asyncio
    async def test_list_users(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list users API
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.ADMIN)

        # act
        response = await client.get(
            url=BASE_ENDPOINT,
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()

        # Check if 'items' key exists in the response
        assert "items" in j_resp

        # Check if 'start', 'end' and 'total' keys exist in the response
        assert "start" in j_resp
        assert "end" in j_resp
        assert "total" in j_resp

        # Check if 'id' key exists in the first item of 'items'
        assert "id" in j_resp["items"][0] and j_resp["items"][0]["id"] == 1

        # Check if 'password' key does not exist in the first item of 'items'
        assert "password" not in j_resp["items"][0]

        # Check if 'groups' key exists in the first item of 'items'
        assert "groups" in j_resp["items"][0]

    @pytest.mark.asyncio
    async def test_list_standalone_users(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list standalone users API.
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.ADMIN)

        # To access this API you will need to be an Admin, meaning you belong to a group so we need to create another
        # user that doesn't belong to any group.
        await self.create_more_users(
            client=client,
            session=session,
            user_name="no-group",
            user_pass="nogrouppass",
        )

        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/standalone",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert len(j_resp) == 1, j_resp
        assert j_resp[0]["id"] == 2
        assert j_resp[0]["name"] == "no-group"
        assert "first_name" in j_resp[0]
        assert "last_name" in j_resp[0]
        assert "enabled" in j_resp[0]

    @pytest.mark.asyncio
    async def test_list_standalone_users_directly_bound_to_perm_no_results(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list standalone users API.
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.ADMIN)
        # create first group and permission
        await self.create_test_permissions(session=session)
        # create new_user
        await self.create_more_users(
            client=client,
            session=session,
            user_name="no-group",
            user_pass="nogrouppass",
        )
        # create permission bound to user 2 and group 1
        # so user 1 has no group
        permission = Permission(
            set_id=1,
            user_id=2,
            group_id=1,
            grant=True,
            list=True,
            read=True,
            write=True,
        )
        session.add(permission)
        await session.commit()
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/standalone",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert not j_resp

    @pytest.mark.asyncio
    async def test_list_standalone_users_has_group_only_one_result(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list standalone users API. Creates a user and binds them to
        a group. API response shall return only one result (the initial
        testuser).
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.ADMIN)
        # create group
        group = Group(name="group")
        session.add(group)
        # create user with group
        user = User(
            name="no-perm",
            first_name="User with group",
            last_name="but no perm",
            password="password",
            api_key=str(uuid4()),
            groups=[group],
        )
        session.add(user)

        # create user without group
        no_group_user = User(
            name="no group",
            first_name="User without group",
            last_name="name",
            password="password",
            api_key=str(uuid4()),
        )
        session.add(no_group_user)

        await session.commit()
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/standalone",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert len(j_resp) == 1
        assert j_resp[0]["id"] == 3
        assert j_resp[0]["name"] == "no group"

    @pytest.mark.asyncio
    async def test_list_standalone_users_with_group_and_permissions(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list standalone users API. Creates a user, binds them to
        a group and assigns permissions. API response should not include this user.
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.ADMIN)

        # create group
        group = Group(name="group")
        session.add(group)
        # create permission
        permission = Permission(
            set_id=1,
            user_id=2,
            group_id=1,
            grant=True,
            list=True,
            read=True,
            write=True,
        )
        session.add(permission)
        # create user
        user = User(
            name="with-group-and-perm",
            first_name="User with group",
            last_name="and perm",
            password="password",
            api_key=str(uuid4()),
            groups=[group],
        )
        session.add(user)

        # create user without group
        no_group_user = User(
            name="no group",
            first_name="User without group",
            last_name="name",
            password="password",
            api_key=str(uuid4()),
        )
        session.add(no_group_user)

        await session.commit()
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/standalone",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert len(j_resp) == 1
        assert j_resp[0]["id"] == 3
        assert j_resp[0]["name"] == "no group"

    @pytest.mark.asyncio
    async def test_list_standalone_users_no_group_with_permissions(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list standalone users API. Creates a user without a group but with
        permissions. API response should not include this user.
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.ADMIN)
        # create permission
        permission = Permission(
            set_id=1,
            user_id=1,
            group_id=None,
            grant=True,
            list=True,
            read=True,
            write=True,
        )
        session.add(permission)
        # create user
        user = User(
            name="no-group-with-perm",
            first_name="User without group",
            last_name="but with perm",
            password="password",
            api_key=str(uuid4()),
        )
        session.add(user)
        await session.commit()
        permission = Permission(
            set_id=1,
            user_id=2,
            group_id=None,
            grant=True,
            list=True,
            read=True,
            write=True,
        )
        session.add(permission)
        # create user without group
        no_group_user = User(
            name="no group",
            first_name="User without group",
            last_name="name",
            password="password",
            api_key=str(uuid4()),
        )
        session.add(no_group_user)

        await session.commit()
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/standalone",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert len(j_resp) == 1
        assert j_resp[0]["id"] == 3
        assert j_resp[0]["name"] == "no group"

    @pytest.mark.asyncio
    async def test_list_users_unauthorized(self, client: AsyncClient):
        """
        Test list users API for unauthorized access
        """
        # act
        response = await client.get(
            url=BASE_ENDPOINT,
            headers={
                "accept": "application/json",
            },
        )
        # assert
        assert (
            response.status_code == status.HTTP_401_UNAUTHORIZED
        ), response.text

    @pytest.mark.asyncio
    async def test_list_users_empty(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list users API when no users exist
        """
        response = await client.get(
            url=BASE_ENDPOINT,
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_403_FORBIDDEN, response.text

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_list_users_invalid_token(self, client: AsyncClient):
        """
        Test list users API with invalid token
        """
        # act
        response = await client.get(
            url=BASE_ENDPOINT,
            headers={
                "accept": "application/json",
                "Authorization": "Bearer invalid_token",
            },
        )
        # assert
        assert (
            response.status_code == status.HTTP_401_UNAUTHORIZED
        ), response.text
        j_resp = response.json()
        assert j_resp["detail"] == {
            "token": (
                "The user's credential is no longer valid."
                " The user must sign in again."
            )
        }

    @pytest.mark.asyncio
    async def test_list_users_details(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list users API for correct user details
        """
        await self.add_role_to_user(session, AuthRole.ADMIN)

        # act
        response = await client.get(
            url=BASE_ENDPOINT,
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()

        # Check if 'items' key exists in the response and is a list
        assert "items" in j_resp and isinstance(j_resp["items"], list)

        # Check if 'start', 'end' and 'total' keys exist in the response
        assert "start" in j_resp
        assert "end" in j_resp
        assert "total" in j_resp

        # Check if first item in 'items' has all required keys
        first_item = j_resp["items"][0]
        assert "id" in first_item
        assert "name" in first_item
        assert "first_name" in first_item
        assert "last_name" in first_item
        assert "enabled" in first_item
        assert "groups" in first_item

    @pytest.mark.asyncio
    async def test_list_inactive_users(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list inactive users API
        """
        count = 5
        users: list[User] = [
            User(
                id=idx,
                name=f"User #{idx}",
                groups=[],
                data_last_accessed=datetime.now(),
            )
            for idx in range(count)
        ]
        session.add_all(users)
        response = await client.get(
            "/{user_id}/inactive",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestGetUsers(AuthTest):
    """
    Test get users API
    """

    # GET USER
    @pytest.mark.asyncio
    async def test_get_user(self, client: AsyncClient, session: AsyncSession):
        """
        Test get user API
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.ADMIN)

        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1
        assert "name" in j_resp and j_resp["name"] == "testuser"
        assert "password" not in j_resp
        assert "groups" in j_resp
        assert "jurisdiction" in j_resp
        assert "organization_name" in j_resp

    # Test for a non-existing user
    @pytest.mark.asyncio
    async def test_get_non_existing_user(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test get user API for a non-existing user
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.ADMIN)

        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/99999",  # assuming this ID does not exist
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_404_NOT_FOUND

    # Test for unauthorized access
    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_get_user_unauthorized(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test get user API for unauthorized access

        Args:
            client (AsyncClient): _description_
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.ADMIN)

        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/1",
            headers={
                "accept": "application/json",
                "Authorization": "Bearer invalid_token",
            },
        )
        # assert
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        j_resp = response.json()
        assert j_resp["detail"] == {
            "token": (
                "The user's credential is no longer valid."
                " The user must sign in again."
            )
        }

    # Test for invalid user ID
    @pytest.mark.asyncio
    async def test_get_user_invalid_id(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test get user API for invalid user ID
        Args:
            client (AsyncClient): _description_
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.ADMIN)

        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/invalid_id",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_get_current_user(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test get user API
        """
        # arrange
        new_user_token = await self.create_more_users(
            client=client,
            session=session,
            user_name="test2",
            user_pass="test2pass",
        )
        await self.add_role_to_user(session, AuthRole.ADMIN, "test2")

        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/current_user",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {new_user_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 2
        assert "name" in j_resp and j_resp["name"] == "test2"
        assert "password" not in j_resp
        assert "groups" in j_resp
        assert "jurisdiction" in j_resp
        assert "organization_name" in j_resp

    @pytest.mark.asyncio
    async def test_unauthorized_access(self, client: AsyncClient):
        """
        Test get user API without token
        """
        response = await client.get(f"{BASE_ENDPOINT}/current_user")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_invalid_token(self, client: AsyncClient):
        """
        Test get user API with invalid token
        """
        response = await client.get(
            url=f"{BASE_ENDPOINT}/current_user",
            headers={
                "accept": "application/json",
                "Authorization": "Bearer invalid_token",
            },
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        j_resp = response.json()
        assert j_resp["detail"] == {
            "token": (
                "The user's credential is no longer valid."
                " The user must sign in again."
            )
        }

    @pytest.mark.asyncio
    async def test_get_user_not_found(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test failure of get users API in case the given ID does not
        match with a record in the DB
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.ADMIN)

        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/999",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestCreateUser(AuthTest):
    """
    Test create user API
    """

    # POST USER
    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_create_user(
        self,
        client: AsyncClient,
        session: AsyncSession,
    ):
        """
        Test create user API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json={
                "name": "usertest",
                "first_name": "Test",
                "last_name": "User",
                "email": "usertest@insomniacdesign.com",
                "api_key": str(uuid4()),
                "password": "T3stpassw0rd",
                "organization_type": OrganizationTypes.FINANCIAL_INSTITUTION,
            },
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 2
        assert (
            "auth_mode" in j_resp and j_resp["auth_mode"] == AuthMode.FIREBASE
        )
        assert j_resp["external_user_id"]
        # await verify_user_email(session, j_resp["id"])

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_create_user_firebase(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create user API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json={
                "name": "usertest",
                "first_name": "Test",
                "last_name": "User",
                "email": "usertest@insomniacdesign.com",
                "api_key": str(uuid4()),
                "password": "T3stpassw0rd",
            },
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 2
        assert (
            "auth_mode" in j_resp and j_resp["auth_mode"] == AuthMode.FIREBASE
        )
        assert "external_user_id" in j_resp

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_create_user_specifies_groups(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create user API with groups specified in the request body
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json={
                "name": "usertest",
                "first_name": "Test",
                "last_name": "User",
                "email": "usertest@insomniacdesign.com",
                "api_key": str(uuid4()),
                "password": "T3stpassw0rd",
                "groups": [
                    {
                        "name": "groupname",
                        "description": "Group description",
                        "delegate_user_id": 1,
                        "delegate_group_id": 1,
                    }
                ],
            },
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 2
        assert (
            "auth_mode" in j_resp and j_resp["auth_mode"] == AuthMode.FIREBASE
        )
        assert (
            "external_user_id" in j_resp
            # and j_resp["external_user_id"] == "reDKbTIEgxYp3mkFPoWhtAhbyth2"
        )

    @pytest.mark.asyncio
    async def test_unauthorized_access(self, client: AsyncClient):
        """
        Test create user API without token
        """
        response = await client.post(f"{BASE_ENDPOINT}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_invalid_user_data(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create user API with invalid user data
        """
        await self.add_admin_permissions_to_user(session)
        response = await client.post(
            url=BASE_ENDPOINT,
            json={
                "name": "",
                "first_name": "",
                "last_name": "",
                "email": None,
                "api_key": str(uuid4()),
                "password": "T3stpassw0rd",
            },
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_duplicate_user(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create user API for duplicate user
        """
        await self.add_admin_permissions_to_user(session)

        # Create first user
        await self.create_more_users(
            client=client,
            session=session,
            user_name="usertest",
            user_pass="T3stpassw0rd",
        )

        # Try to create second user with same details and catch the exception
        try:
            await self.create_more_users(
                client=client,
                session=session,
                user_name="usertest",
                user_pass="T3stpassw0rd",
            )
        except HTTPException as exc:
            error = exc
            # Check if the status code of the exception is 409 (Conflict)
            assert error.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.asyncio
    async def test_empty_user_data(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create user API with empty user data
        """
        await self.add_admin_permissions_to_user(session)
        response = await client.post(
            url=BASE_ENDPOINT,
            json={},
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestUpdateUser(AuthTest):
    """
    Test update user API
    """

    # UPDATE USER
    @pytest.mark.asyncio
    async def test_update_user_base(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update user API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/1",
            json={
                "name": "newname",
                "jurisdiction": "test_jurisdiction",
                "organization_name": "test_organization",
                "organization_type": "Other",
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1
        # here we check successful update of record
        assert j_resp["name"] == "newname"
        assert j_resp["jurisdiction"] == "test_jurisdiction"
        assert j_resp["organization_name"] == "test_organization"
        assert j_resp["organization_type"] == "Other"
        assert j_resp["token"] == self.access_token
        assert j_resp["refresh_token"] is None

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_update_local_user_password_success(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update password on local user.
        """

        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # load old password
        db_user = await session.scalar(select(User).where(User.id == 1))
        assert db_user
        old_password_encrypted = db_user.password

        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/1",
            json={
                "new_password": "Testp4ssword",
                "current_password": "T3stpassw0rd",
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1
        # here we check successful update of record
        assert j_resp["name"] == "testuser"
        # check password has updated
        session.expire_all()  # refresh DB state
        db_user_updated = await session.scalar(
            select(User).where(User.id == 1)
        )
        assert db_user_updated
        assert db_user_updated.password != old_password_encrypted  # type: ignore

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_update_local_user_password_invalid_old_password_fail(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update password on local user.
        """

        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # load old password
        db_user = await session.scalar(select(User).where(User.id == 1))
        assert db_user
        old_password_encrypted = db_user.password

        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/1",
            json={
                "new_password": "Testp4ssword",
                "current_password": "notthecurrentpassword",
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert (
            response.status_code == status.HTTP_400_BAD_REQUEST
        ), response.text
        # check password is kept
        session.expire_all()  # refresh DB state
        db_user_updated = await session.scalar(
            select(User).where(User.id == 1)
        )
        assert db_user_updated
        assert db_user_updated.password == old_password_encrypted  # type: ignore

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_update_firebase_user_password_success(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update password on firebase user.
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        user_create_payload = UserCreate(
            name="fb_user",
            email="test@user.com",
            first_name="firebase",
            last_name="user",
            api_key="apikey",
            password="T3stpassw0rd",
        )  # type: ignore
        # create firebase user
        user_create = await client.post(
            url=BASE_ENDPOINT,
            json=user_create_payload.dict(),
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert user_create.status_code == status.HTTP_200_OK, user_create.text
        await verify_user_email(session, user_create.json()["id"])

        # get token for new user
        response = await client.post(
            "/token", data={"username": "fb_user", "password": "T3stpassw0rd"}
        )
        assert response.status_code == status.HTTP_200_OK, response.json()
        new_user_token = response.json()["access_token"]

        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/2",
            json={
                "new_password": "Testp4ssword",
                "current_password": "T3stpassw0rd",
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {new_user_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 2
        # here we check successful update of record
        assert j_resp["name"] == "fb_user"
        # assert j_resp["token"] != new_user_token
        assert j_resp["refresh_token"] is not None
        # check password has updated
        response = await client.post(
            "/token", data={"username": "fb_user", "password": "Testp4ssword"}
        )
        assert response.status_code == status.HTTP_200_OK, response.json()
        session.expire_all()  # refresh DB state
        db_user_updated = await session.scalar(
            select(User).where(User.id == 2)
        )
        assert db_user_updated
        assert db_user_updated.password is None  # type: ignore

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_update_firebase_user_password_invalid_old_password_fail(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update user API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        user_create_payload = UserCreate(
            name="fb_user",
            email="test@user.com",
            first_name="firebase",
            last_name="user",
            api_key="apikey",
            password="T3stpassw0rd",
        )  # type: ignore
        # create firebase user
        user_create = await client.post(
            url=BASE_ENDPOINT,
            json=user_create_payload.dict(),
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert user_create.status_code == status.HTTP_200_OK, user_create.text
        await verify_user_email(session, user_create.json()["id"])

        # load old password
        db_user = await session.scalar(select(User).where(User.id == 2))
        assert db_user
        old_password_encrypted = db_user.password

        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/2",
            json={
                "new_password": "Testp4ssword",
                "current_password": "notthecurrentpassword",
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert (
            response.status_code == status.HTTP_400_BAD_REQUEST
        ), response.text
        j_resp = response.json()
        assert j_resp["detail"] == {
            "password": (
                "Incorrect password. Please try again or reset your"
                " password."
            )
        }
        # check password is kept
        session.expire_all()  # refresh DB state
        db_user_updated = await session.scalar(
            select(User).where(User.id == 2)
        )
        assert db_user_updated
        assert db_user_updated.password == old_password_encrypted  # type: ignore

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_update_firebase_user_email(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update user API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        user_create_payload = UserCreate(
            name="fb_user",
            email="test@user.com",
            first_name="firebase",
            last_name="user",
            api_key="apikey",
            password="T3stpassw0rd",
        )  # type: ignore
        # create firebase user
        user_create = await client.post(
            url=BASE_ENDPOINT,
            json=user_create_payload.dict(),
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert user_create.status_code == status.HTTP_200_OK, user_create.text
        await verify_user_email(session, user_create.json()["id"])

        # get token for new user
        response = await client.post(
            "/token", data={"username": "fb_user", "password": "T3stpassw0rd"}
        )
        assert response.status_code == status.HTTP_200_OK, response.json()
        new_user_token = response.json()["access_token"]

        # load old email
        db_user = await session.get(User, 2)
        assert db_user
        old_email = db_user.email

        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/2",
            json={"email": "new@email.com"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {new_user_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 2
        # here we check successful update of record
        assert j_resp["name"] == "fb_user"
        assert j_resp["email"] == "new@email.com"
        assert j_resp["token"] != new_user_token
        assert j_resp["refresh_token"] is not None
        # check password has updated
        session.expire_all()  # refresh DB state
        db_user_updated = await session.scalar(
            select(User).where(User.id == 2)
        )
        assert db_user_updated
        assert db_user_updated.email != old_email  # type: ignore

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_update_firebase_user_not_found_in_firebase_raise(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update user API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        user_create_payload = UserCreate(
            name="fb_user",
            email="test@user.com",
            first_name="firebase",
            last_name="user",
            api_key="apikey",
            password="T3stpassw0rd",
        )  # type: ignore
        # create firebase user
        user_create = await client.post(
            url=BASE_ENDPOINT,
            json=user_create_payload.model_dump(),
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert user_create.status_code == status.HTTP_200_OK, user_create.text
        await verify_user_email(session, user_create.json()["id"])

        # get token for new user
        response = await client.post(
            "/token", data={"username": "fb_user", "password": "T3stpassw0rd"}
        )
        assert response.status_code == status.HTTP_200_OK, response.json()
        new_user_token = response.json()["access_token"]

        # delete firebase user list
        project_id = settings.gcp.project
        httpxdelete(
            url=f"http://localhost:9099/emulator/v1/projects/{project_id}/accounts"
        )

        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/2",
            json={"email": "new@email.com"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {new_user_token}",
            },
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
    async def test_update_user_with_groups(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update user API with groups
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/1",
            json={
                "name": "newname",
                "groups": [
                    {
                        "name": "test group",
                        "description": "group for testing",
                        "delegate_user_id": 1,
                        "delegate_group_id": 1,
                    }
                ],
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1
        # here we check successful update of record
        assert j_resp["name"] == "newname"

        assert len(j_resp["groups"]) == 2
        assert j_resp["groups"][1]["name"] == "test group"

    @pytest.mark.asyncio
    async def test_update_user_not_found(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update user API, user not found raises 404
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/999",
            json={
                "name": "newname",
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_update_user_without_admin_permissions(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update user API without admin permissions
        """
        # act
        await self.add_admin_permissions_to_user(session)
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/1",
            json={
                "name": "newname",
                "jurisdiction": "test_jurisdiction",
                "organization_name": "test_organization",
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_update_user_with_invalid_data(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update user API with invalid data (invalid email format)
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/1",
            json={
                "email": "testingmail.com",
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert (
            response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        ), response.text

    @pytest.mark.asyncio
    async def test_update_user_with_no_changes(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test update user API with no changes
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # act
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/1",
            json={},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert "id" in j_resp and j_resp["id"] == 1

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_update_user_email_firebase_same_user(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test updating user email, updates user email in firebase.

        Also calls firebase_admin.auth.get_user to check email has
        changed in Firebase's user database.

        In this test the user requesting the update is the same user as
        the updated user.
        """

        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # create firebase user
        old_email = "usertest@insomniacdesign.com"
        response = await client.post(
            url=BASE_ENDPOINT,
            json={
                "name": "usertest",
                "first_name": "Test",
                "last_name": "User",
                "email": old_email,
                "api_key": str(uuid4()),
                "password": "T3stpassw0rd",
                "auth_mode": 2,
            },
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.json()
        await verify_user_email(session, response.json()["id"])
        # get token for new user
        response = await client.post(
            "/token", data={"username": "usertest", "password": "T3stpassw0rd"}
        )
        assert response.status_code == status.HTTP_200_OK, response.json()
        new_user_token = response.json()["access_token"]

        # act
        new_email = "testuser@insomniacdesign.com"
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/2",
            json={
                "email": new_email,
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {new_user_token}",
            },
        )

        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert j_resp["token"] != new_user_token
        assert j_resp["refresh_token"] is not None
        # load information from firebase to ensure email changed
        firebase_auth_client = initialize_firebase_auth_client()
        with firebase_auth_client as _fb:
            f_user = _fb.get_user(j_resp["external_user_id"])
        assert f_user.email == new_email
        assert not f_user.email_verified

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_update_user_email_firebase_different_admin_user(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test updating user email, updates user email in firebase.

        Also calls firebase_admin.auth.get_user to check email has
        changed in Firebase's user database.

        In this test the user requesting the update is an admin
        performing the update on another user.
        """

        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # create firebase user
        old_email = "usertest@insomniacdesign.com"
        response = await client.post(
            url=BASE_ENDPOINT,
            json={
                "name": "usertest",
                "first_name": "Test",
                "last_name": "User",
                "email": old_email,
                "api_key": str(uuid4()),
                "password": "T3stpassw0rd",
                "auth_mode": 2,
            },
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )

        # act
        new_email = "testuser@insomniacdesign.com"
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/2",
            json={
                "email": new_email,
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        # for some weird reason, firebase emulator from CLI returns 500,
        # while firebase emulator from docker returns 404
        assert response.status_code != status.HTTP_200_OK, response.text

    @pytest.mark.asyncio
    async def test_user_request_publisher_access(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Tests user publisher access request.
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.ADMIN)

        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/request-publisher-access",
            json={"company_lei": "000012345678"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert j_resp["status"] == "requested"

    @pytest.mark.asyncio
    async def test_notification_signup(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test get user API
        """
        await self.add_admin_permissions_to_user(session=session)

        # act
        response = await client.post(
            url=f"{BASE_ENDPOINT}/notifications-signup",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert "user_id" in j_resp and j_resp["user_id"] == 1
        assert "notifications" in j_resp and j_resp["notifications"] is True

    @pytest.mark.asyncio
    async def test_notification_signup_download(
        self, client: AsyncClient, session: AsyncSession
    ):
        await self.add_admin_permissions_to_user(session)
        await client.post(
            url=f"{BASE_ENDPOINT}/notifications-signup",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        response = await client.get(
            url=f"{BASE_ENDPOINT}/notifications-signup/download",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        csv_content_str = response.content.decode("utf-8")
        csv_reader = csv.reader(csv_content_str.splitlines())
        headers = next(csv_reader)
        data_row = next(csv_reader)

        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "application/octet-stream"
        assert (
            response.headers["content-disposition"]
            == 'attachment; filename="nzdpu_users_with_notification.csv"'
        )
        assert headers == ["user_id", "email"]
        assert len(data_row) == 2

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_grant_user_with_schema_editor_group(
        self, client: AsyncClient, session: AsyncSession
    ):
        group = Group(name=AuthRole.SCHEMA_EDITOR)
        session.add(group)
        await session.flush()
        await self.add_admin_permissions_to_user(session)

        user_name, user_password = str(uuid4()), str(uuid4())
        user_email = f"{user_name}@nzdpu.com"
        new_user_token = await self.create_more_users(
            client, session, user_name, user_password, user_email
        )
        assert new_user_token

        response = await client.post(
            url=f"{BASE_ENDPOINT}/admin-grant",
            json={"email": user_email},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        result = response.json()

        user_db = await session.execute(
            select(User)
            .options(selectinload(User.groups))
            .where(User.email == user_email)
        )

        user = user_db.scalar_one()
        assert response.status_code == status.HTTP_200_OK
        assert user.groups[0].name == result["role"] == AuthRole.SCHEMA_EDITOR
        assert user.id in result["user_id"]

    @pytest.mark.asyncio
    async def test_grant_user_with_schema_editor_group_if_email_domain_not_nzdpu_return_bad_request(
        self, client: AsyncClient, session: AsyncSession
    ):
        group = Group(name=AuthRole.SCHEMA_EDITOR)
        session.add(group)
        await session.commit()
        await self.add_admin_permissions_to_user(session)

        user_name, user_password = str(uuid4()), str(uuid4())
        user_email = f"{user_name}@gmail.com"
        new_user_token = await self.create_more_users(
            client, session, user_name, user_password
        )
        assert new_user_token

        response = await client.post(
            url=f"{BASE_ENDPOINT}/admin-grant",
            json={"email": user_email},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        result = response.json()

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert result["detail"]["email"]

    @pytest.mark.asyncio
    async def test_grant_user_with_schema_editor_group_if_already_admin_returns_bad_request(
        self, client: AsyncClient, session: AsyncSession
    ):
        group = Group(name=AuthRole.SCHEMA_EDITOR)
        session.add(group)
        await session.commit()
        await self.add_role_to_user(
            session=session, role_name=AuthRole.SCHEMA_EDITOR
        )
        response = await client.post(
            url=f"{BASE_ENDPOINT}/admin-grant",
            json={"email": self.email},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        result = response.json()
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert result["detail"]["email"]


class TestUserAccessKey(AuthTest):
    """
    Test get and revoke user api_key
    """

    # GET USER
    @pytest.mark.asyncio
    async def test_get_and_revoke_access_key(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test get user access key
        """
        # arrange
        await self.add_admin_permissions_to_user(session=session)
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/get-access-key",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert "access_key" in j_resp
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/revoke-access-key",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert j_resp["access_key"] == ""


class TestDeleteUser(AuthTest):
    """
    Test deleting users
    """

    @pytest.mark.asyncio
    async def test_delete_user(
        self, client: AsyncClient, session: AsyncSession
    ):
        # act
        await self.add_admin_permissions_to_user(session)
        response = await client.delete(
            url=f"{BASE_ENDPOINT}/1",
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp["id"] == 1
        assert j_resp["deleted"]

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_delete_firebase_user(
        self, client: AsyncClient, session: AsyncSession
    ):
        # act
        await self.add_admin_permissions_to_user(session)
        # create firebase user
        response = await client.post(
            url=BASE_ENDPOINT,
            json={
                "name": "usertest",
                "first_name": "Test",
                "last_name": "User",
                "email": "test@user.com",
                "api_key": str(uuid4()),
                "password": "T3stpassw0rd",
                "auth_mode": 2,
            },
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # load user for further verification
        db_user = await session.get(User, 2)
        # act
        response = await client.delete(
            url=f"{BASE_ENDPOINT}/2",
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp["id"] == 2
        assert j_resp["deleted"]
        with pytest.raises(HTTPException):
            firebase_auth_client = initialize_firebase_auth_client()
            with firebase_auth_client as _fb:
                _fb.get_user(db_user.external_user_id)

    @firebase
    @pytest.mark.firebase
    @pytest.mark.asyncio
    async def test_delete_firebase_user_not_found(
        self, client: AsyncClient, session: AsyncSession
    ):
        # act
        await self.add_admin_permissions_to_user(session)
        # create firebase user
        response = await client.post(
            url=BASE_ENDPOINT,
            json={
                "name": "usertest",
                "first_name": "Test",
                "last_name": "User",
                "email": "test@user.com",
                "api_key": str(uuid4()),
                "password": "T3stpassw0rd",
                "auth_mode": 2,
            },
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # load user
        db_user = await session.get(User, 2)
        assert db_user
        # delete user in firebase
        with initialize_firebase_auth_client() as _fb:
            _fb.delete_user(db_user.external_user_id)
        # act
        response = await client.delete(
            url=f"{BASE_ENDPOINT}/2",
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp["id"] == 2
        assert j_resp["deleted"]
        with pytest.raises(HTTPException):
            firebase_auth_client = initialize_firebase_auth_client()
            with firebase_auth_client as _fb:
                _fb.get_user(db_user.external_user_id)


class TestPasswordValidation(AuthTest):
    """
    Test password validation
    """

    @pytest.mark.asyncio
    async def test_is_valid_password_length(self):
        """
        this test for test length of password
        """
        create_user = {
            "name": "usertest",
            "first_name": "Test",
            "last_name": "User",
            "email": "test@user.com",
            "api_key": str(uuid4()),
            "password": "passtest",
        }
        response = is_valid_password(
            create_user["password"],
            create_user["name"],
            True,
            create_user["email"],
        )

        assert response == "Password must be at least 12 characters long."

    @pytest.mark.asyncio
    async def test_is_valid_password_not_match_username(self):
        """
        this test for test password not match with username
        """
        create_user = {
            "name": "usertest2345fe",
            "first_name": "Test",
            "last_name": "User",
            "email": "test@user.com",
            "api_key": str(uuid4()),
            "password": "usertest2345fe",
        }
        response = is_valid_password(
            create_user["password"],
            create_user["name"],
            True,
            create_user["email"],
        )

        assert response == "Password must not be the same as the username."

    @pytest.mark.asyncio
    async def test_is_valid_password(self):
        """
        this test for test password not match with username
        """
        create_user = {
            "name": "usertest",
            "first_name": "Test",
            "last_name": "User",
            "email": "test@user.com",
            "api_key": str(uuid4()),
            "password": "usertest2345fe",
        }
        response = is_valid_password(
            create_user["password"],
            create_user["name"],
            True,
            create_user["email"],
        )

        assert (
            response == "Password should contain two of the following: "
            "uppercase letter, lowercase letter, "
            "number or punctuation marks."
        )


class TestDownloadTrackingDataUsers(AuthTest):
    @pytest.mark.asyncio
    async def test_download_without_permissions(self, client):
        response = await client.get(
            url=f"{BASE_ENDPOINT}/tracking/download",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_download_with_admin_permissions(self, client, session):
        await self.add_admin_permissions_to_user(session)
        response = await client.get(
            url=f"{BASE_ENDPOINT}/tracking/download",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "text/csv; charset=utf-8"

    @pytest.mark.asyncio
    async def test_verify_csv_data(self, client, session):
        await self.add_admin_permissions_to_user(session)
        await session.execute(
            update(User)
            .where(User.name == self.user_name)
            .values(email="testadmin@email.com")
        )

        user = (
            await session.execute(
                select(User.id, User.email).where(User.name == self.user_name)
            )
        ).first()

        await session.execute(
            insert(Tracking).values(
                id=1,
                user_email=user.email,
                api_endpoint="/test-api",
                date_time=datetime.strptime(
                    "2024-09-04 12:59:03.566656", "%Y-%m-%d %H:%M:%S.%f"
                ),
                source="WEB",
                result=123,
            )
        )

        response = await client.get(
            url=f"{BASE_ENDPOINT}/tracking/download",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        csv_content_str = response.content.decode("utf-8")
        csv_file_like = io.StringIO(csv_content_str)
        csv_reader = csv.reader(csv_file_like)
        for i, row in enumerate(csv_reader):
            if i == 0:
                assert row == [
                    "user_email",
                ]
            else:
                assert row == [
                    user.email,
                ]
