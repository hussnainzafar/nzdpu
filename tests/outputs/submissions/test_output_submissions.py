"""
Test submissions output
"""

import json
from functools import reduce
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings
from app.db.models import Organization, SubmissionObj, TableView
from app.db.redis import RedisClient
from app.schemas.enums import SICSSectorEnum
from app.service.core.cache import CoreMemoryCache
from app.service.core.loaders import SubmissionLoader
from tests.constants import (
    SCHEMA_FILE_NAME,
    SUBMISSION_SCHEMA_COMPANIES_FILE_NAME,
)
from tests.routers.auth_test import AuthTest
from tests.routers.test_companies import create_organization
from tests.routers.utils import NZ_ID, create_test_form

data_dir: Path = settings.BASE_DIR.parent / "tests/data"


@pytest.fixture
def submission_mock():
    """
    Fixture for submission mock
    Returns
    -------
    submissions mock
    """
    with open(data_dir / SUBMISSION_SCHEMA_COMPANIES_FILE_NAME) as f:
        return {
            "table_view_id": 1,
            "permissions_set_id": 1,
            "values": json.load(f),
        }


class TestSubmisionsOutput(AuthTest):
    """
    Test to ensure response from submissions api match the schema
    """

    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, session: AsyncSession):
        await self.create_test_permissions(session)
        await self.add_admin_permissions_to_user(session)
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)

    @pytest.fixture
    def submission_loader(
        self,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
        redis_client: RedisClient,
    ):
        return SubmissionLoader(session, static_cache, redis_client)

    @property
    def headers(self):
        return {
            "content-type": "application/json",
            "accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }

    def get_attribute_names(self, attrs: list[dict[str, Any]]):
        return [attr.get("name") for attr in attrs]

    async def get_sub_schema_attrs(
        self, session: AsyncSession, client: AsyncClient, sub_id: int
    ) -> list[dict[str, Any]]:
        submission: SubmissionObj = (
            await session.scalars(
                select(SubmissionObj).where(SubmissionObj.id == sub_id)
            )
        ).first()
        table_view: TableView = await session.scalar(
            select(TableView).where(TableView.id == submission.table_view_id)
        )
        schema_response = await client.get(
            "/schema/full",
            params={"table_id": table_view.table_def_id},
            headers=self.headers,
        )
        return schema_response.json()["attributes"]

    async def keys_match_schema(
        self,
        id: int,
        attrs: list[dict[str, Any]],
        values: list[dict[str, Any]],
        loader: SubmissionLoader,
    ) -> bool:
        data = await loader.load(id, db_only=True)
        val_keys = reduce(
            lambda prev, next: set(prev) ^ set(next),
            [data.values.keys()] + [val.keys() for val in values],
        )
        unique_keys = val_keys - set(self.get_attribute_names(attrs))
        return len(unique_keys ^ {"id", "obj_id"}) == 0

    async def create_submission_organization(
        self, lei: str, session: AsyncSession, nz_id: int = NZ_ID
    ):
        organization = Organization(
            lei=lei,
            nz_id=nz_id,
            legal_name=str(uuid4()),
            jurisdiction="US-MA",
            sics_sector=SICSSectorEnum.INFRASTRUCTURE,
            sics_sub_sector="subsector",
            sics_industry="sics_industry",
        )
        session.add(organization)
        await session.commit()

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_create_submission(
        self,
        client: AsyncClient,
        static_cache: CoreMemoryCache,
        session: AsyncSession,
        submission_mock,
        submission_loader,
    ):
        await self.create_submission_organization(
            submission_mock["values"]["legal_entity_identifier"],
            session,
            nz_id=1001,
        )
        await static_cache.refresh_values()
        submission_create_response = await client.post(
            url="/submissions",
            json=submission_mock,
            headers=self.headers,
        )

        submission_create_result = submission_create_response.json()

        attributes = await self.get_sub_schema_attrs(
            session, client, submission_create_result["id"]
        )
        matched = await self.keys_match_schema(
            id=submission_create_result["id"],
            attrs=attributes,
            values=[
                submission_create_result["values"],
            ],
            loader=submission_loader,
        )
        assert matched

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_get_submission(
        self,
        client: AsyncClient,
        static_cache: CoreMemoryCache,
        session: AsyncSession,
        submission_mock,
        submission_loader,
    ):
        await self.create_submission_organization(
            submission_mock["values"]["legal_entity_identifier"],
            session,
            nz_id=1001,
        )
        submission_created = await client.post(
            url="/submissions",
            json=submission_mock,
            headers=self.headers,
        )
        await static_cache.refresh_values()

        submission_create_result = submission_created.json()

        attributes = await self.get_sub_schema_attrs(
            session, client, submission_create_result["id"]
        )
        submission_id = submission_create_result["id"]

        submission_get_response = await client.get(
            url=f"/submissions/{submission_id}",
            headers=self.headers,
        )

        submission_get_result = submission_get_response.json()

        matched = await self.keys_match_schema(
            id=submission_id,
            attrs=attributes,
            values=[
                submission_get_result["values"],
            ],
            loader=submission_loader,
        )
        assert matched

    @pytest.mark.asyncio
    async def test_list_submissions(
        self,
        client: AsyncClient,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
        submission_mock,
        submission_loader,
    ):
        await self.create_submission_organization(
            "0EEB8GF0W0NPCIHZX097", session, nz_id=1001
        )

        submission_created = await client.post(
            url="/submissions",
            json=submission_mock,
            headers=self.headers,
        )

        assert submission_created.status_code == status.HTTP_200_OK

        # prepare second submission
        new_lei = "00KLB2PFTM3060S2N216"
        await self.create_submission_organization(new_lei, session, nz_id=1002)
        submission_mock["values"]["legal_entity_identifier"] = new_lei
        await static_cache.refresh_values()

        # create second submission
        second_submission_created = await client.post(
            url="/submissions", json=submission_mock, headers=self.headers
        )

        assert second_submission_created.status_code == status.HTTP_200_OK

        list_response = await client.get(
            url="/submissions",
            headers=self.headers,
        )
        submission_list = list_response.json()["items"]
        for sub in submission_list:
            attributes = await self.get_sub_schema_attrs(
                session, client, sub["id"]
            )
            matched = await self.keys_match_schema(
                id=sub["id"],
                attrs=attributes,
                values=[
                    sub["values"],
                ],
                loader=submission_loader,
            )
            assert matched

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_update_submission(
        self,
        client: AsyncClient,
        static_cache: CoreMemoryCache,
        session: AsyncSession,
        submission_mock,
        submission_loader,
    ):
        await static_cache.refresh_values()
        values = submission_mock.pop("values")
        submission_mock["values"] = {}

        submission_create_response = await client.post(
            url="/submissions",
            json=submission_mock,
            headers=self.headers,
        )
        submission_create_result = submission_create_response.json()
        assert submission_create_response.status_code == status.HTTP_200_OK

        submission_update_response = await client.patch(
            url=f"submissions/{submission_create_result['id']}",
            json={"values": values},
            headers=self.headers,
        )
        submission_update_result = submission_update_response.json()

        attributes = await self.get_sub_schema_attrs(
            session, client, submission_update_result["id"]
        )

        matched = await self.keys_match_schema(
            id=submission_update_result["id"],
            attrs=attributes,
            values=[
                submission_create_result["values"],
                submission_update_result["values"],
            ],
            loader=submission_loader,
        )
        assert matched

    @pytest.mark.asyncio
    async def test_get_latest_reporting_year(
        self,
        client: AsyncClient,
        static_cache: CoreMemoryCache,
        submission_mock,
        session: AsyncSession,
    ):
        await self.create_submission_organization(
            submission_mock["values"]["legal_entity_identifier"],
            session,
            nz_id=1001,
        )
        await static_cache.refresh_values()
        await client.post(
            url="/submissions",
            json=submission_mock,
            headers=self.headers,
        )
        resp = await client.get(
            url="/submissions/latest-reporting-year/", headers=self.headers
        )

        last_year_data = resp.json()
        assert resp.status_code == status.HTTP_200_OK
        assert last_year_data == {
            "year": submission_mock["values"]["reporting_year"]
        }
