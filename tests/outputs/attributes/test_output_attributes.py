"""Output tests for attributes"""

import json
import os
from datetime import datetime

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings
from app.db.models import AuthRole, ColumnDef
from app.schemas.column_def import ColumnDefCreate
from tests.routers.auth_test import AuthTest
from tests.routers.utils import create_test_table_def


class TestAttributes(AuthTest):
    """
    Unit tests for attributes APIs
    """

    async def create_test_attribute(self, session: AsyncSession, **kwargs):
        """
        Creates an attribute in the DB for testing purposes
        """
        attribute_schema = ColumnDefCreate(
            name=kwargs.get("name", "test attribute"),
            table_def_id=kwargs.get("table_def_id", 1),
            created_on=kwargs.get("created_on", datetime.now()),
            user_id=kwargs.get("user_id", None),
            attribute_type=kwargs.get("attribute_type", "text"),
            attribute_type_id=kwargs.get("attribute_type_id", None),
            choice_set_id=kwargs.get("choice_set_id", None),
        )
        attribute = ColumnDef(**attribute_schema.model_dump())
        session.add(attribute)
        await session.commit()

    # LIST ATTRIBUTES
    @pytest.mark.asyncio
    async def test_list_attributes(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list attributes with schema
        """
        file_path = os.path.join(
            settings.BASE_DIR,
            ("../tests/outputs/attributes/get_attributes.json"),
        )

        with open(file_path, "r") as file:
            data = json.load(file)
        # arrange

        await create_test_table_def(session)
        for each in data["items"]:
            await self.create_test_attribute(session, **each)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # act
        response = await client.get(
            "/schema/attributes?start=0&limit=10",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert "start" in j_resp and j_resp["start"] == 0
        assert "end" in j_resp and j_resp["end"] == 4
        assert "total" in j_resp and j_resp["total"] == 4
        assert "items" in j_resp
        items = j_resp["items"]
        assert isinstance(items, list)
        assert len(items) == 4
        assert j_resp == data

    # POST ATTRIBUTE
    @pytest.mark.asyncio
    async def test_create_and_get_update_and_attribute(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test create, get and  update  attribute API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_table_def(session)
        # act
        response = await client.post(
            url="/schema/attributes",
            json={
                "name": "new_attribute",
                "table_def_id": 1,
                "created_on": "2023-10-16T16:17:53.458636",
                "user_id": 1,
                "attribute_type": "label",
                "attribute_type_id": 0,
                "choice_set_id": 0,
            },
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp == {
            "name": "new_attribute",
            "table_def_id": 1,
            "created_on": "2023-10-16T16:17:53.458636",
            "user_id": 1,
            "attribute_type": "label",
            "attribute_type_id": 0,
            "choice_set_id": 0,
            "id": 1,
        }

        # GET ATTRIBUTE
        # act
        response = await client.get(
            "/schema/attributes/1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert'
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        assert j_resp == {
            "name": "new_attribute",
            "table_def_id": 1,
            "created_on": "2023-10-16T16:17:53.458636",
            "user_id": 1,
            "attribute_type": "label",
            "attribute_type_id": 0,
            "choice_set_id": 0,
            "id": 1,
        }

        # update attribute

        # act
        response = await client.patch(
            url="/schema/attributes/1",
            json={
                "name": "new_attribute_testing",
                "table_def_id": 1,
                "created_on": "2023-10-16T16:17:53.458636",
                "user_id": 1,
                "attribute_type": "text",
                "attribute_type_id": 0,
                "choice_set_id": 0,
            },
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()

        assert j_resp == {
            "name": "new_attribute_testing",
            "table_def_id": 1,
            "created_on": "2023-10-16T16:17:53.458636",
            "user_id": 1,
            "attribute_type": "text",
            "attribute_type_id": 0,
            "choice_set_id": 0,
            "id": 1,
        }
