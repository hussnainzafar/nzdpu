"""Auth test"""

from uuid import uuid4

import pytest_asyncio
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import AuthRole, Group, Organization, Permission, User
from app.schemas.enums import SICSSectorEnum
from app.utils import encrypt_password
from tests.routers.utils import NZ_ID


class AuthTest:
    """
    Base class for unit tests that require an authenticate used
    """

    user_name: str = "testuser"
    user_pass: str = "T3stpassw0rd"
    group_name: str = "testgroup"
    admin_group_name: AuthRole = AuthRole.ADMIN
    email: str = "testuser@gmail.com"
    # pytest: disable = unsupported-binary-operation
    access_token: str | None = None

    @pytest_asyncio.fixture(autouse=True)
    async def create_test_user(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Create user record for testing
        """

        # create test organization
        organization = Organization(
            lei="000012345678",
            legal_name="testorg",
            jurisdiction="US-MA",
            sics_sector=SICSSectorEnum.INFRASTRUCTURE,
            sics_sub_sector="subsector",
            sics_industry="sics_industry",
            nz_id=NZ_ID,
        )
        session.add(organization)
        await session.flush()

        # create test user
        encrypted_pwd = encrypt_password(self.user_pass)
        user = User(
            name=self.user_name,
            first_name="Test",
            last_name="User",
            email=self.email,
            email_verified=True,
            password=encrypted_pwd,
            api_key=str(uuid4()),
            organization_id=organization.id,
        )
        session.add(user)
        await session.commit()

        # request a token for user
        response = await client.post(
            "/token", data={"username": self.email, "password": self.user_pass}
        )
        if response.status_code == 200:
            j_resp = response.json()
            self.access_token = j_resp["access_token"]

    @staticmethod
    async def create_more_users(
        client: AsyncClient,
        session: AsyncSession,
        user_name: str,
        user_pass: str,
        user_email: str = "",
        organization_id: int = None,
    ):
        """
        Create user record for testing
        """

        last_user_id = 0
        stmt = select(User).where(User.name == user_name)
        existing_user = await session.scalar(stmt)

        # Check if user already exists
        if existing_user is not None:
            raise HTTPException(status_code=409, detail="Duplicate user")

        stmt = select(User).order_by(User.id.desc())
        last_user = await session.scalar(stmt)
        if last_user is not None:
            last_user_id = last_user.id

        user_email = user_email or f"{user_name}@gmail.com"

        # create test user
        encrypted_pwd = encrypt_password(user_pass)
        user = User(
            name=user_name,
            first_name=f"Test {last_user_id}",
            last_name="User",
            email=user_email,
            password=encrypted_pwd,
            api_key=str(uuid4()),
        )
        if organization_id is not None:
            user.organization_id = organization_id
        session.add(user)
        await session.commit()

        # request a token for user
        response = await client.post(
            "/token", data={"username": user.email, "password": user_pass}
        )
        if response.status_code == 200:
            j_resp = response.json()
            return j_resp["access_token"]

    async def create_test_permissions(self, session: AsyncSession) -> int:
        """
        Create permissions data for testing
        Parameters
        ----------
        session - database session
        Returns
        -------
        permissions set identifier
        """

        # create test group
        group = Group(name=self.group_name)
        session.add(group)
        await session.flush()

        # load test user
        result = await session.execute(
            select(User)
            .options(selectinload(User.groups))
            .where(User.name == self.user_name)
        )
        user = result.scalars().first()
        assert user
        user.groups.append(group)

        # create permissions for user and group
        permissions_set_id: int = 1
        session.add_all(
            [
                Permission(
                    set_id=permissions_set_id,
                    group_id=group.id,
                    grant=True,
                    list=True,
                    read=True,
                    write=True,
                ),
                Permission(
                    set_id=permissions_set_id,
                    user_id=user.id,
                    grant=True,
                    list=True,
                    read=True,
                    write=False,
                ),
            ]
        )

        # commit transaction
        await session.commit()

        return permissions_set_id

    async def add_role_to_user(
        self,
        session: AsyncSession,
        role_name: str,
        user_name: str | None = None,
    ):
        if not user_name:
            user_name = self.user_name

        # Create group if it doesn't exist already
        stmt = select(Group).where(Group.name == role_name)
        result = await session.execute(stmt)
        group = result.scalars().first()

        # If group doesn't exist, create it
        if not group:
            group = Group(name=role_name)
            session.add(group)
            await session.flush()

        # Load test user
        result = await session.execute(
            select(User)
            .options(selectinload(User.groups))
            .where(User.name == user_name)
        )
        user = result.scalars().first()
        assert user
        user.groups.append(group)
        session.add(user)

        # Commit transaction
        await session.commit()

    async def add_admin_permissions_to_user(self, session: AsyncSession):
        """
        Create admin permission for testing
        Parameters
        ----------
        session - database session
        """

        await self.add_role_to_user(session, self.admin_group_name)
