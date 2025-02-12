"""Unit tests for choices router"""

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.db.models import AuthRole, Choice
from app.schemas.choice import ChoiceCreate, ChoiceCreateSet
from tests.routers.auth_test import AuthTest


class TestChoices(AuthTest):
    """
    Unit tests for choices APIs
    """

    @pytest.mark.asyncio
    async def test_list_choices(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List choices" API
        """
        # create test choices
        count: int = 15
        page_size: int = 5
        pages: int = count // page_size + (count % page_size > 0)
        choices: list[Choice] = [
            Choice(
                choice_id=idx,
                set_id=1,
                set_name="Test Set",
                value=f"Choice #{idx}",
                description=f"Test choice #{idx}",
                order=idx,
                language_code="en_US",
            )
            for idx in range(count)
        ]
        session.add_all(choices)
        await session.commit()
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)

        # Test with set_id parameter
        for page in range(1, pages + 1):
            start = (page - 1) * page_size

            # send request
            response = await client.get(
                "/schema/choices",
                params={"set_id": 1, "start": start, "limit": page_size},
                headers={
                    "accept": "application/json",
                    "Authorization": f"Bearer {self.access_token}",
                },
            )

            assert response.status_code == 200, response.text
            j_resp = response.json()
            assert j_resp["items"]
            assert j_resp["end"] - j_resp["start"] == min(
                page_size, count - start
            )
            assert all(item["set_id"] == 1 for item in j_resp["items"])

        # Test without set_id parameter
        response = await client.get(
            "/schema/choices",
            params={"start": 0, "limit": count},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert j_resp["end"] - j_resp["start"] == count
        assert all(item["set_id"] == 1 for item in j_resp["items"])

        # Test pagination
        response = await client.get(
            "/schema/choices",
            params={"start": 5, "limit": 5},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert j_resp["end"] - j_resp["start"] == 5
        assert all(item["set_id"] == 1 for item in j_resp["items"])

    @pytest.mark.asyncio
    async def test_get_choice_when_choice_exists(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test case for when the choice exists in the database.

        This test case creates a new choice with id 1 and value "Choice #1",
        then it sends a GET request to the endpoint with the id of the created choice.
        It asserts that the status code of the response is 200 and the content of the response is as expected.
        """
        choice: Choice = Choice(
            choice_id=1, set_id=1, set_name="Test Set", value="Choice #1"
        )
        session.add(choice)
        await session.commit()
        record_id: int = choice.id
        await self.add_role_to_user(session, AuthRole.SCHEMA_EDITOR)

        # send request
        response = await client.get(
            f"/schema/choices/{record_id}",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert j_resp["id"] == 1

    @pytest.mark.asyncio
    async def test_get_choice_set_by_name(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test case for when the choice set exists in the database.

        This test case creates a new choice set with name "Test Set",
        then it sends a GET request to the endpoint with the name of the created choice set.
        It asserts that the status code of the response is 200 and the content of the response is as expected.
        """
        choice: Choice = Choice(
            choice_id=1,
            set_id=1,
            set_name="Test Set",
            value="Choice #1",
            language_code="en_US",
        )
        session.add(choice)
        await session.commit()
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        set_name: str = choice.set_name
        # send request
        response = await client.get(
            f"schema/choices/sets/by-name?name={set_name}",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert j_resp["set_id"] == 1
        assert j_resp["set_name"] == "Test Set"
        assert j_resp["language_code"] == "en_US"
        assert j_resp["labels"] == ["Choice #1"]

    @pytest.mark.asyncio
    async def test_get_choice_set_by_name_with_multiple_value(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test case for when the choice set exists in the database.

        This test case creates a new choice set with name "Test Set",
        then it sends a GET request to the endpoint with the name of the created choice set.
        It asserts that the status code of the response is 200 and the content of the response is as expected.
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create input schema
        schema = ChoiceCreateSet(
            set_name="Test Set", labels=["Choice #1", "Choice #2", "Choice #3"]
        )
        # send request
        response = await client.post(
            "/schema/choices/set",
            json=schema.model_dump(),
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "set_id" in j_resp and j_resp["set_id"] == 1

        # send request
        response = await client.get(
            f"schema/choices/sets/by-name?name={schema.set_name}",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert j_resp["set_id"] == 1
        assert j_resp["set_name"] == "Test Set"
        assert j_resp["language_code"] == "en_US"
        assert j_resp["labels"] == ["Choice #1", "Choice #2", "Choice #3"]

    @pytest.mark.asyncio
    async def test_get_choice_when_choice_does_not_exist(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test case for when the choice does not exist in the database.

        This test case sends a GET request to the endpoint with a non-existent id (9999 in this case).
        It asserts that an HTTPException is raised with status code 404 and detail "Choice not found".
        """
        # Arrange
        non_existent_id = 9999

        # Act
        try:
            await client.get(
                f"/schema/choices/{non_existent_id}",
                headers={
                    "accept": "application/json",
                    "Authorization": f"Bearer {self.access_token}",
                },
            )
        except HTTPException as exc:
            # Assert
            assert exc.status_code == 404
            assert str(exc.detail) == "Choice not found"

    @pytest.mark.asyncio
    async def test_create_choice(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Create choice" API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # set choice schema
        choice_schema = ChoiceCreate(
            choice_id=1,
            set_id=1,
            set_name="Test Set",
            value="Test choice",
            description="Test description",
            order=1,
            language_code="en_US",
        )
        # send request
        response = await client.post(
            "/schema/choices",
            json=choice_schema.model_dump(),
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "choice_id" in j_resp and j_resp["choice_id"] == 1
        assert "set_id" in j_resp and j_resp["set_id"] == 1
        assert "set_name" in j_resp and j_resp["set_name"] == "Test Set"
        assert "value" in j_resp and j_resp["value"] == "Test choice"
        assert (
            "description" in j_resp
            and j_resp["description"] == "Test description"
        )
        assert "order" in j_resp and j_resp["order"] == 1
        assert "language_code" in j_resp and j_resp["language_code"] == "en_US"

    @pytest.mark.asyncio
    async def test_create_choice_without_admin_permissions(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Create choice" API without admin permissions
        """
        # set choice schema
        choice_schema = ChoiceCreate(
            choice_id=1,
            set_id=1,
            set_name="Test Set",
            value="Test choice",
            description="Test description",
            order=1,
            language_code="en_US",
        )
        # send request
        response = await client.post(
            "/schema/choices",
            json=choice_schema.model_dump(),
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == 403, response.text

    @pytest.mark.asyncio
    async def test_create_choice_with_duplicate_data(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Create choice" API with duplicate data
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # set choice schema
        choice_schema = ChoiceCreate(
            choice_id=1,
            set_id=1,
            set_name="Test Set",
            value="Test choice",
            description="Test description",
            order=1,
            language_code="en_US",
        )
        # create choice
        db_choice = Choice(**choice_schema.model_dump())
        session.add(db_choice)
        await session.commit()

        # send request with the same data
        response = await client.post(
            "/schema/choices",
            json=choice_schema.model_dump(),
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 422, response.text

    @pytest.mark.asyncio
    async def test_create_choice_no_id(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Create choice" API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # set choice schema
        choice_schema = ChoiceCreate(
            set_id=1, value="Test choice", set_name="Test Set"
        )
        # send request
        response = await client.post(
            "/schema/choices",
            json=choice_schema.model_dump(),
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert (
            "choice_id" in j_resp
            and j_resp["choice_id"] == Choice.CHOICE_ID_AUTO_START
        )
        assert "set_id" in j_resp and j_resp["set_id"] == 1
        assert "value" in j_resp and j_resp["value"] == "Test choice"

    @pytest.mark.asyncio
    async def test_update_choice(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Update choice" API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create test choice
        choice: Choice = Choice(
            choice_id=1, set_id=1, value="Choice #1", set_name="Test Set"
        )
        session.add(choice)
        await session.commit()
        choice_id: int = choice.id
        # send request
        response = await client.patch(
            f"/schema/choices/{choice_id}",
            json={"value": "Choice #1 - Rev 2"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "choice_id" in j_resp and j_resp["choice_id"] == 1
        assert "value" in j_resp and j_resp["value"] == "Choice #1 - Rev 2"

    @pytest.mark.asyncio
    async def test_update_choice_invalid_user(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Update choice" API with a user without admin permissions
        """
        # create test choice
        choice: Choice = Choice(
            choice_id=1, set_id=1, set_name="Test Set", value="Choice #1"
        )
        session.add(choice)
        await session.commit()
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        choice_id: int = choice.id

        # send request
        response = await client.patch(
            f"/schema/choices/{choice_id}",
            json={"value": "Choice #1 - Rev 2"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 403, response.text

    @pytest.mark.asyncio
    async def test_update_choice_non_existing_id(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Update choice" API with non-existing choice id
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # send request
        response = await client.patch(
            "/schema/choices/9999",
            json={"value": "Choice #1 - Rev 2"},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 404, response.text

    @pytest.mark.asyncio
    async def test_update_choice_empty_data(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Update choice" API with empty update data
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create test choice
        choice: Choice = Choice(
            choice_id=1, set_id=1, set_name="Test Set", value="Choice #1"
        )
        session.add(choice)
        await session.commit()
        choice_id: int = choice.id

        # send request
        response = await client.patch(
            f"/schema/choices/{choice_id}",
            json={},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == 200, response.text

    @pytest.mark.asyncio
    async def test_create_choice_set(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Create choice set" API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create input schema
        schema = ChoiceCreateSet(
            set_name="Test Set", labels=["Choice #1", "Choice #2", "Choice #3"]
        )

        # send request
        response = await client.post(
            "/schema/choices/set",
            json=schema.model_dump(),
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert "set_id" in j_resp and j_resp["set_id"] == 1

    @pytest.mark.asyncio
    async def test_list_choice_sets(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List choice sets" API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create input schema and populate database with some choice sets
        for i in range(5):
            schema = ChoiceCreateSet(
                set_name=f"Test Set{i}",
                labels=[f"Choice #{i+1}", f"Choice #{i+2}", f"Choice #{i+3}"],
            )
            response = await client.post(
                "/schema/choices/set",
                json=schema.model_dump(),
                headers={
                    "accept": "application/json",
                    "Authorization": f"Bearer {self.access_token}",
                },
            )
            assert response.status_code == 200, response.text

        # send request to list choice sets
        response = await client.get(
            "schema/choices/sets?limit=5&start=0",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200, response.text
        j_resp = response.json()

        # check if the response has the correct keys
        assert all(key in j_resp for key in ["start", "end", "total", "items"])

        # check if the items are correctly grouped by set_id
        for item in j_resp["items"]:
            assert "set_id" in item and len(item["choices"]) >= 2

    @pytest.mark.asyncio
    async def test_create_multiple_choice_sets(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Create choice set" API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create input schema for Set 1
        schema_set01 = ChoiceCreateSet(
            set_name="Test Set",
            labels=[
                "Set 1 - Choice #1",
                "Set 1 - Choice #2",
                "Set 1 - Choice #3",
            ],
        )

        # send request
        response = await client.post(
            "/schema/choices/set",
            json=schema_set01.model_dump(),
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert "set_id" in j_resp and j_resp["set_id"] == 1

        # create input schema for Set 2
        schema_set02 = ChoiceCreateSet(
            set_name="Test Set 2",
            labels=[
                "Set 2 - Choice #1",
                "Set 2 - Choice #2",
                "Set 2 - Choice #3",
            ],
        )

        # send request
        response = await client.post(
            "/schema/choices/set",
            json=schema_set02.model_dump(),
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert "set_id" in j_resp and j_resp["set_id"] == 2

    @pytest.mark.asyncio
    async def test_create_choice_set_invalid_user(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Create choice set" API with a user without admin permissions
        """
        # create input schema
        schema = ChoiceCreateSet(
            set_name="test name",
            labels=["Choice #1", "Choice #2", "Choice #3"],
        )

        # send request
        response = await client.post(
            "/schema/choices/set",
            json=schema.model_dump(),
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 403, response.text

    @pytest.mark.asyncio
    async def test_create_choice_set_empty_labels(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Create choice set" API with empty labels
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create input data with empty labels
        data = {"labels": [], "language_code": "en_US"}

        # send request
        response = await client.post(
            "/schema/choices/set",
            json=data,
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 422, response.text

    @pytest.mark.asyncio
    async def test_create_choice_set_duplicate_labels(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "Create choice set" API with duplicate labels
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create input data with duplicate labels
        data = {"labels": ["Choice #1", "Choice #1"], "language_code": "en_US"}

        # send request
        response = await client.post(
            "/schema/choices/set",
            json=data,
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 422, response.text

    @pytest.mark.asyncio
    async def test_list_choices_with_multilanguage_content(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test list choices API with multilanguage content
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # define test data with multilanguage content
        test_data = [
            {
                "language_code": "en-US",
                "set_name": "Test Set1",
                "value": "test_choice",
                "description": "test_choice_desc",
            },
            {
                "language_code": "zh-CN",
                "set_name": "Test Set2",
                "value": "测试选择",
                "description": "测试选择描述",
            },
            {
                "language_code": "fr-FR",
                "set_name": "Test Set3",
                "value": "choix de test",
                "description": "description du choix de test",
            },
            {
                "language_code": "de-DE",
                "set_name": "Test Set4",
                "value": "test_auswahl",
                "description": "test_auswahl_beschreibung",
            },
            {
                "language_code": "es-ES",
                "set_name": "Test Set5",
                "value": "opción de prueba",
                "description": "descripción de opción de prueba",
            },
            {
                "language_code": "ru-RU",
                "set_name": "Test Set6",
                "value": "тестовый выбор",
                "description": "описание тестового выбора",
            },
            {
                "language_code": "ja-JP",
                "set_name": "Test Set7",
                "value": "テスト選択肢",
                "description": "テスト選択肢の説明",
            },
            {
                "language_code": "ar-SA",
                "set_name": "Test Set8",
                "value": "خيار الاختبار",
                "description": "وصف خيار الاختبار",
            },
            {
                "language_code": "el-GR",
                "set_name": "Test Set9",
                "value": "επιλογή δοκιμής",
                "description": "περιγραφή επιλογής δοκιμής",
            },
        ]

        # create choices in database
        for i, data in enumerate(test_data):
            choice_schema = ChoiceCreate(
                choice_id=i + 1,
                value=data["value"],
                set_name=data["set_name"],
                description=data["description"],
                language_code=data["language_code"],
                set_id=1,
            )
            response = await client.post(
                "/schema/choices",
                json=choice_schema.model_dump(),
                headers={
                    "accept": "application/json",
                    "Authorization": f"Bearer {self.access_token}",
                },
            )

            assert response.status_code == 200, response.text

        response = await client.get(
            "/schema/choices",
            params={"set_id": 1},
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        # assert
        assert response.status_code == 200, response.text
        j_resp = response.json()
        assert (
            "choice_id" in j_resp["items"][0]
            and j_resp["items"][0]["choice_id"] == 1
        )
        assert (
            "language_code" in j_resp["items"][0]
            and j_resp["items"][0]["language_code"] == "en-US"
        )
        assert (
            "value" in j_resp["items"][0]
            and j_resp["items"][0]["value"] == "test_choice"
        )
        assert (
            "choice_id" in j_resp["items"][1]
            and j_resp["items"][1]["choice_id"] == 2
        )
        assert (
            "language_code" in j_resp["items"][1]
            and j_resp["items"][1]["language_code"] == "zh-CN"
        )
        assert (
            "value" in j_resp["items"][1]
            and j_resp["items"][1]["value"] == "测试选择"
        )
        assert (
            "choice_id" in j_resp["items"][2]
            and j_resp["items"][2]["choice_id"] == 3
        )
        assert (
            "language_code" in j_resp["items"][2]
            and j_resp["items"][2]["language_code"] == "fr-FR"
        )
        assert (
            "value" in j_resp["items"][2]
            and j_resp["items"][2]["value"] == "choix de test"
        )
        assert (
            "choice_id" in j_resp["items"][3]
            and j_resp["items"][3]["choice_id"] == 4
        )
        assert (
            "language_code" in j_resp["items"][3]
            and j_resp["items"][3]["language_code"] == "de-DE"
        )
        assert (
            "value" in j_resp["items"][3]
            and j_resp["items"][3]["value"] == "test_auswahl"
        )
        assert (
            "choice_id" in j_resp["items"][4]
            and j_resp["items"][4]["choice_id"] == 5
        )
        assert (
            "language_code" in j_resp["items"][4]
            and j_resp["items"][4]["language_code"] == "es-ES"
        )
        assert (
            "value" in j_resp["items"][4]
            and j_resp["items"][4]["value"] == "opción de prueba"
        )
        assert (
            "choice_id" in j_resp["items"][5]
            and j_resp["items"][5]["choice_id"] == 6
        )
        assert (
            "language_code" in j_resp["items"][5]
            and j_resp["items"][5]["language_code"] == "ru-RU"
        )
        assert (
            "value" in j_resp["items"][5]
            and j_resp["items"][5]["value"] == "тестовый выбор"
        )
        assert (
            "choice_id" in j_resp["items"][6]
            and j_resp["items"][6]["choice_id"] == 7
        )
        assert (
            "language_code" in j_resp["items"][6]
            and j_resp["items"][6]["language_code"] == "ja-JP"
        )
        assert (
            "value" in j_resp["items"][6]
            and j_resp["items"][6]["value"] == "テスト選択肢"
        )
        assert (
            "choice_id" in j_resp["items"][7]
            and j_resp["items"][7]["choice_id"] == 8
        )
        assert (
            "language_code" in j_resp["items"][7]
            and j_resp["items"][7]["language_code"] == "ar-SA"
        )
        assert (
            "value" in j_resp["items"][7]
            and j_resp["items"][7]["value"] == "خيار الاختبار"
        )
        assert (
            "choice_id" in j_resp["items"][8]
            and j_resp["items"][8]["choice_id"] == 9
        )
        assert (
            "language_code" in j_resp["items"][8]
            and j_resp["items"][8]["language_code"] == "el-GR"
        )
        assert (
            "value" in j_resp["items"][8]
            and j_resp["items"][8]["value"] == "επιλογή δοκιμής"
        )

    @pytest.mark.asyncio
    async def test_list_choice_sets_filter_by_validation_success(
        self, client: AsyncClient, session: AsyncSession
    ):
        """
        Test "List choice sets" API
        """
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # create input schema and populate database with some choice sets
        for i in range(5):
            schema = ChoiceCreateSet(
                set_name=f"Test Set{i}",
                labels=[f"Choice #{i+1}", f"Choice #{i+2}", f"Choice #{i+3}"],
            )
            response = await client.post(
                "/schema/choices/set",
                json=schema.model_dump(),
                headers={
                    "accept": "application/json",
                    "Authorization": f"Bearer {self.access_token}",
                },
            )
            assert response.status_code == 200, response.text

        # send request to list choice sets
        response = await client.get(
            'schema/choices/sets?limit=5&start=0&filter_by={"chice_id": 1}',
            # params={
            #     "limit": 5,
            #     "start": 0,
            #     "filter_by": {
            #         "choice_id": 1
            #     }
            # }
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == 200, response.text
        j_resp = response.json()

        # check if the response has the correct keys
        assert all(key in j_resp for key in ["start", "end", "total", "items"])

        # check if the items are correctly grouped by set_id
        for item in j_resp["items"]:
            assert "set_id" in item and len(item["choices"]) >= 2
