"""Unit tests for sumission router"""

import json
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app import settings
from app.db.models import (
    AggregatedObjectView,
    AuthRole,
    ColumnDef,
    ColumnView,
    SubmissionObj,
    TableView,
)
from app.schemas.enums import SubmissionObjStatusEnum
from app.service.core.cache import CoreMemoryCache
from app.service.submission_builder import SubmissionBuilder
from tests.constants import SCHEMA_FILE_NAME, SUBMISSION_SCHEMA_FILE_NAME
from tests.routers.auth_test import AuthTest
from tests.routers.test_companies import create_organization

from .utils import NZ_ID, create_test_form

BASE_ENDPOINT = "/submissions"
data_dir: Path = settings.BASE_DIR.parent / "tests/data"

firebase = pytest.mark.skipif("not config.getoption('firebase')")

# pylint: disable = invalid-name, line-too-long, redefined-outer-name, self-assigning-variable


@pytest.fixture
def submission_payload():
    """
    Fixture for submission payload
    Returns
    -------
    submissions payload
    """
    with open(data_dir / SUBMISSION_SCHEMA_FILE_NAME) as f:
        return {
            "nz_id": NZ_ID,
            "table_view_id": 1,
            "permissions_set_id": 1,
            "values": json.load(f),
        }


@pytest.fixture
def submission_create_payload():
    """
    Fixture for submission create payload
    Returns
    -------
    submissions payload
    """
    with open(data_dir / "form-create-sub.json") as f:
        return {
            "nz_id": NZ_ID,
            "table_view_id": 1,
            "permissions_set_id": 1,
            "values": json.load(f),
        }


# ref: https://en.wikipedia.org/wiki/Wikipedia:Language_recognition_chart
special_characters_latin = (
    "àäèéëïĳöü",  # dutch
    "áêéèëïíîôóúû",  # afrikaans
    "êôúû",  # west frisian
    "ÆØÅæøå",  # danish, norwegian
    "ÄÖäö",  # finnish
    "ÅÄÖåäö",  # swedish
    "ÄÖÕÜäöõü",  # estonian
    "ÄÖÜẞäöüß",  # german
    "ÇÊÎŞÛçêîşû",  # kurdish
    "ĂÂÎȘȚăâîșț",  # romanian
    "ÓÚẂÝÀÈÌÒÙẀỲÄËÖÜẄŸóúẃýàèìòùẁỳäëöüẅÿ",  # welsh
    "ĈĜĤĴŜŬĉĝĥĵŝŭ",  # esperanto
    "ÇĞİÖŞÜçğıöşü",  # turkish
    "ÁÐÉÍÓÚÝÞÆÖáðéíóúýþæö",  # icelandic
    "ÁÐÍÓÚÝÆØáðíóúýæø",  # faroese
    "ÁÉÍÓÖŐÚÜŰáéíóöőúüű",  # hungarian
    "ÀÇÉÈÍÓÒÚÜÏàçéèíóòúüï·",  # catalan
    "ÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸàâæçéèêëîïôœùûüÿ",  # french
    "ÁÀÇÉÈÍÓÒÚËÜÏáàçéèíóòúëüï·",  # occitan
    "ÁÉÍÓÚÂÊÔÀãõçáéíóúâêôàü",  # portuguese, brazilian
    "ÁÉÍÑÓÚÜáéíñóúü¡¿",  # spanish
    "ÀÉÈÌÒÙàéèìòù",  # italian
    "ÁÉÍÓÚÝÃẼĨÕŨỸÑG̃áéíóúýãẽĩõũỹñg̃",  # guarani
    "ÁĄĄ́ÉĘĘ́ÍĮĮ́ŁŃáąą́éęę́íįį́łń",  # southern athabaskan languages
    "ÓǪǪ́āą̄ēę̄īį̄óōǫǫ́ǭúū",  # western apache
    "ÓǪǪ́óǫǫ́",  # navajo
    "ÚŲŲ́úųų́",  # chiricahua/mescalero
    "ąłńóż",  # lechitic languages
    "ćęłńóśźż",  # polish
    "ćśůź",  # silesian
    "AĄÃBCDEÉËFGHIJKLŁMNŃOÒÓÔPRSTUÙWYZŻČŠŽãéëòôù",  # kashubian
    "ĆĐ",  # bosnian, croatian, serbian latin
    "ÁĎÉĚÍŇÓŘŤÚŮÝáďéěíňóřťúůý",  # czech
    "ÁÄĎÉÍĽĹŇÓÔŔŤÚÝáäďéíľĺňóôŕťúý",  # slovak
    "ĀĒĢĪĶĻŅŌŖŪāēģīķļņōŗū",  # latvian
    "ĄĘĖĮŲŪąęėįųū",  # lithuanian
    (  # vietnamese
        "ĐÀẢÃÁẠĂẰẲẴẮẶÂẦẨẪẤẬÈẺẼÉẸÊỀỂỄẾỆÌỈĨÍỊÒỎÕÓỌÔỒỔỖỐỘƠỜỞỠỚỢÙỦŨÚỤƯỪỬỮỨỰỲỶỸÝỴđàảãáạăằẳẵắặâầẩ"
        "ẫấậèẻẽéẹêềểễếệìỉĩíịòỏõóọồổỗốơờởỡớợùủũúụưừửữứựỳỷỹýỵ"
    ),
    "ꞗĕŏŭo᷄ơ᷄u᷄",  # middle vietnamese
    "āēīōū",  # japanese
    "é",  # sundanese
    "ñ",  # basque
)

special_characters_latin = "".join(
    sorted(set("".join(special_characters_latin)))
)  # length 300

special_characters_other = (
    "ابتثجحخدذرزسشصضطظعغفقكلمنهوي",  # arabic
    "پچژگ",  # persian (farsi)
    "অআকাকিকীউকুঊকূঋকৃএকেঐকৈওকোঔকৌক্কত্‍কংকঃকঁকখগঘঙচছজঝঞটঠডঢণতথদধনপফবভমযরৰলৱশষসহয়ড়ঢ়০১২৩৪৫৬৭৮৯",  # bengali
    "अआइईउऊऋॠऌॡऍऎएऐऑऒओओकखगघङचछजझञटठडढणतथदधनपफबभमयरलळवशषसह०१२३४५६७८९प्पँपंपःप़पऽ",  # devanāgarī
    "ਅਆਇਈਉਊਏਐਓਔਕਖਗਘਙਚਛਜਝਞਟਠਡਢਣਤਥਦਧਨਪਫਬਭਮਯਰਲਲ਼ਵਸ਼ਸਹ",  # gurmukhi
    "અઆઇઈઉઊઋઌઍએઐઑઓઔકખગઘઙચછજઝઞટઠડઢણતથદધનપફબભમયરલળવશષસહૠૡૢૣ",  # gujarati
    "ཀཁགངཅཆཇཉཏཐདནཔཕབམཙཚཛཝཞཟའཡརལཤསཧཨ",  # tibetan
    "АБВГДЕЖЗИКЛМНОПРСТУФХЦЧШЙЩЬЮЯЪЁЫЭЎІҐЪҐЄІЇЉЊЏЈЃЌЅЋЂ",  # cyrillic (bulgarian, belarussian, russian,
    # ukranian, macedonian, serbian)
    "ЄꙂꙀЗІЇꙈОуꙊѠЩЪꙐЬѢЮꙖѤѦѨѪѬѮѰѲѴҀ",  # old church slavonic, church slavonic
    "Ӂ",  # romanian in transnistria
    "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩαβγδεζηθικλμνξοπρσςτυφχψω",  # greek
    "ואבגדהוזחטיכלמנסעפצקרשתפֿיא",  # hebrew, yiddish, aramaic, ladino
    "漢字文化圈",  # chinese,
    "あいうえおのアイウエオノ",  # japanese (hiragana, katakana)
    "위키백과에",  # korean
    "ㄅㄆㄇㄈㄉㄊㄋㄌㄍㄎㄏㄓㄨˋㄧㄣㄈㄨˊㄏㄠˋ",  # bopomofo
    "ㄪㄫㄬ",  # not mandarin
    "កខគឃងចឆជឈញដឋឌឍណតថទធនបផពភមសហយរលឡអវអ្កអ្ខអ្គអ្ឃអ្ងអ្ចអ្ឆអ្ឈអ្ញអ្ឌអ្ឋអ្ឌអ្ឃអ្ណអ្តអ្ថអ្ទអ្ធអ្នអ្បអ្ផអ្ពអ្ភអ្មអ្សអ្ហអ្យអ្រអ្យអ្លអ្អអ្វអក្សរខ្មែរ",  # khmer
    "ԱԲԳԴԵԶԷԸԹԺԻԼԽԾԿՀՁՂՃՄՅՆՇՈՉՊՋՌՍՎՏՐՑՒՓՔՕՖ",  # armenian
    "აბგდევზჱთიკლმნჲოპჟრსტჳუფქღყშჩცძწჭხჴჯჰჵჶჷჸ",  # georgian
    "กขฃคฅฆงจฉชซฌญฎฏฐฑฒณดตถทธนบปผฝพฟภมยรฤลฦวศษสหฬอฮฯะา฿เแโใไๅๆ๏๐๑๒๓๔๕๖๗๘๙๚๛",  # thai
    "AEIOUHKLMNPW",  # hawaiian
    "ⴰⴱⴲⴳⴴⴵⴶⴷⴸⴹⴺⴻⴼⴽⴾⴿⵀⵁⵂⵃⵄⵅⵆⵇⵈⵉⵊⵋⵌⵍⵎⵐⵑⵒⵓⵔⵕⵖⵗⵘⵙⵚⵛⵜⵝⵞⵠⵡⵢⵣⵤⵥⵦⵧ",  # tifinagh
)

special_characters_other = "".join(
    sorted(set("".join(special_characters_other)))
)  # length 725


class TestSubmissionsList(AuthTest):
    """
    Unit tests for submissions APIs
    """

    # LIST SUBMISSIONS

    @pytest.mark.asyncio
    async def test_list_submissions(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
    ):
        """
        Test list Submissions API
        """
        # create test permissions
        set_id: int = await self.create_test_permissions(session)
        # add admin permissions
        # await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        builder = SubmissionBuilder(
            cache=redis_client, session=session, static_cache=static_cache
        )

        await builder.generate(
            nz_id=NZ_ID,
            table_view_id=1,
            permissions_set_id=set_id,
            tpl_file=SUBMISSION_SCHEMA_FILE_NAME,
        )
        await builder.generate(
            nz_id=NZ_ID,
            table_view_id=1,
            permissions_set_id=set_id,
            tpl_file=SUBMISSION_SCHEMA_FILE_NAME,
        )
        await builder.generate(
            nz_id=NZ_ID,
            table_view_id=1,
            permissions_set_id=set_id,
            tpl_file=SUBMISSION_SCHEMA_FILE_NAME,
        )

        # act

        response = await client.get(
            url=BASE_ENDPOINT,
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        j_resp = response.json()

        # assert
        assert response.status_code == 200
        assert len(j_resp["items"]) == 3
        assert j_resp["items"][0]["values"]

        # Test pagination
        response = await client.get(
            url=f"{BASE_ENDPOINT}?start=1&limit=2",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        j_resp = response.json()

        # assert
        assert response.status_code == status.HTTP_200_OK
        assert len(j_resp["items"]) == 2
        assert j_resp["start"] == 1
        assert j_resp["end"] == 3

        # Test invalid pagination
        response = await client.get(
            url=f"{BASE_ENDPOINT}?start=5&limit=2",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        j_resp = response.json()
        # assert
        assert response.status_code == status.HTTP_200_OK
        assert len(j_resp["items"]) == 0

    # 1. Test case for an empty list of submissions
    @pytest.mark.asyncio
    async def test_list_submissions_empty(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
    ):
        """_summary_

        Args:
            client (AsyncClient): _description_
        """
        await self.add_role_to_user(session, AuthRole.DATA_EXPLORER)
        await static_cache.refresh_values()
        response = await client.get(
            url=BASE_ENDPOINT,
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "start": 0,
            "end": 0,
            "total": 0,
            "items": [],
        }

    # 2. Test case for invalid table_view_id
    @pytest.mark.asyncio
    async def test_list_submissions_invalid_table_view_id(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
    ):
        """_summary_

        Args:
            client (AsyncClient): _description_
        """
        await self.add_role_to_user(session, AuthRole.DATA_EXPLORER)
        await static_cache.refresh_values()
        response = await client.get(
            url=f"{BASE_ENDPOINT}?table_view_id=-999",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert (
            len(response.json()["items"]) == 0
        )  # or whatever your application returns in this case


class TestGetSubmissions(AuthTest):
    """
    Unit tests for submissions APIs
    """

    # GET SUBMISSION
    @pytest.mark.asyncio
    async def test_get_submission(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
    ):
        """
        Test get Submission API
        """

        # create test permissions
        set_id: int = await self.create_test_permissions(session)

        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        builder = SubmissionBuilder(
            cache=redis_client, session=session, static_cache=static_cache
        )
        await builder.generate(
            table_view_id=1,
            nz_id=NZ_ID,
            permissions_set_id=set_id,
            tpl_file=SUBMISSION_SCHEMA_FILE_NAME,
            no_change=True,
        )
        await self.add_role_to_user(session, AuthRole.DATA_EXPLORER)
        await static_cache.refresh_values()
        # act
        response = await client.get(
            url=f"{BASE_ENDPOINT}/1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        j_resp = response.json()
        # assert
        assert response.status_code == status.HTTP_200_OK
        assert j_resp["values"]
        assert j_resp["submitted_by"] == 1
        assert j_resp["status"] == SubmissionObjStatusEnum.DRAFT

    @pytest.mark.asyncio
    async def test_get_submission_not_found(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
    ):
        """
        Test get Submission API
        """
        # arrange
        await self.add_role_to_user(session, AuthRole.DATA_EXPLORER)
        await static_cache.refresh_values()
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

    # Test case for invalid submission_id
    @pytest.mark.asyncio
    async def test_get_submission_invalid_id(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
    ):
        """
        Test get Submission API with invalid submission_id
        """
        await self.add_role_to_user(session, AuthRole.DATA_EXPLORER)
        await static_cache.refresh_values()

        response = await client.get(
            url=f"{BASE_ENDPOINT}/-1",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert (
            response.status_code == 404
        )  # or whatever your application returns in this case


class TestCreateSubmissions(AuthTest):
    """
    Unit tests for submissions APIs
    """

    # CREATE SUBMISSION
    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_create_submission(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        submission_payload,
    ):
        """
        Test create Submission API
        """
        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # create test permissions
        await self.create_test_permissions(session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        await create_organization(
            session=session,
            lei="0EEB8GF0W0NPCIHZX097",
            legal_name="Test Org 1",
            jurisdiction="Test Org 1",
            nz_id=1001,
        )
        await static_cache.refresh_values()

        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        j_resp = response.json()
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        assert j_resp["id"]
        assert j_resp["active"]
        submission = await session.scalar(
            select(SubmissionObj).where(SubmissionObj.id == j_resp["id"])
        )
        assert submission
        assert submission.user_id is None
        assert submission.status == SubmissionObjStatusEnum.DRAFT
        assert submission.lei == "0EEB8GF0W0NPCIHZX097"

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_create_submission_with_sqlalchemy_error(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        submission_payload,
    ):
        """
        Test create Submission API with SQL Alchemy 422 error
        """
        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # create test permissions
        await self.create_test_permissions(session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        await static_cache.refresh_values()

        # add wrong attribute for error to replicate
        submission_payload["values"]["scope_1_ghg_breakdown"][0][
            "disclose_s1_ghg_other_yn"
        ] = False

        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        j_resp = response.json()
        # assert
        assert (
            response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        ), response.text
        assert j_resp["detail"] == {
            "error": (
                "Database error occurred Unconsumed column names: disclose_s1_ghg_other_yn"
            )
        }

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_create_submission_with_quoted_text(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        submission_payload,
    ):
        """
        Test create Submission API
        """
        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # create test permissions
        await self.create_test_permissions(session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        await create_organization(
            session=session,
            lei="0EEB8GF0W0NPCIHZX097",
            legal_name="Test Org 1",
            jurisdiction="Test Org 1",
            nz_id=1001,
        )

        await static_cache.refresh_values()

        # act
        submission_payload["values"]["s1_emissions_exclusion_dict"][0][
            "s1_emissions_exclusion_desc"
        ] = "The value's quotes should be escaped"
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        j_resp = response.json()
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        assert j_resp["id"]
        assert j_resp["active"]
        submission = await session.scalar(
            select(SubmissionObj).where(SubmissionObj.id == j_resp["id"])
        )
        assert submission
        assert submission.user_id is None
        assert submission.status == SubmissionObjStatusEnum.DRAFT
        assert submission.lei == "0EEB8GF0W0NPCIHZX097"

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_same_user_create_same_submission_two_different_leis(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        submission_payload,
    ):
        """
        Test create Submission API
        """
        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # create test permissions
        await self.create_test_permissions(session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        await create_organization(
            session,
            "0EEB8GF0W0NPCIHZX097",
            "Test Org 1",
            "Test Org 1",
            nz_id=1001,
        )
        await create_organization(
            session,
            "123WALMHY1GZXG2YDL90",
            "Test Org 1",
            "Test Org 1",
            nz_id=1002,
        )

        await static_cache.refresh_values()

        # act
        # first submission
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        j_resp = response.json()
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        assert j_resp["id"]
        assert j_resp["active"]
        submission = await session.scalar(
            select(SubmissionObj).where(SubmissionObj.id == j_resp["id"])
        )
        assert submission
        assert submission.user_id is None
        assert submission.status == SubmissionObjStatusEnum.DRAFT
        assert submission.lei == "0EEB8GF0W0NPCIHZX097"
        # second submission
        submission_payload["values"]["legal_entity_identifier"] = (
            "123WALMHY1GZXG2YDL90"
        )
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        j_resp = response.json()
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        assert j_resp["id"]
        assert j_resp["active"]
        submission = await session.scalar(
            select(SubmissionObj).where(SubmissionObj.id == j_resp["id"])
        )
        assert submission
        assert submission.user_id is None
        assert submission.status == SubmissionObjStatusEnum.DRAFT
        assert submission.lei == "123WALMHY1GZXG2YDL90"

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_create_submission_with_null_special_value(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        submission_payload,
    ):
        """
        Test create Submission API with null special
            value SINGLE, MULTIPLE AND SUB-FORMS
        """
        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # create test permissions
        await self.create_test_permissions(session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        await create_organization(
            session=session,
            lei="0EEB8GF0W0NPCIHZX097",
            legal_name="Test Org 1",
            jurisdiction="Test Org 1",
            nz_id=1001,
        )
        await static_cache.refresh_values()
        submission_payload["values"]["s1_ch4_emissions"] = -999999
        # There are no multiple fields in schema v4.0
        # submission_payload["values"]["scope_1_change_type"] = [-999999]
        submission_payload["values"]["s1_emissions_exclusion_dict"] = [-999999]
        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        j_resp = response.json()
        # assert
        assert response.status_code == status.HTTP_200_OK, response.text
        assert j_resp["id"]
        assert j_resp["active"]
        assert j_resp["values"]["s1_ch4_emissions"] == -999999
        # There are no multiple fields in schema v4.0
        # assert j_resp["values"]["scope_1_change_type"] == [-999999]
        assert j_resp["values"]["s1_emissions_exclusion_dict"] == [-999999]
        submission = await session.scalar(
            select(SubmissionObj).where(SubmissionObj.id == j_resp["id"])
        )
        assert submission
        assert submission.user_id is None
        assert submission.status == SubmissionObjStatusEnum.DRAFT
        assert submission.lei == "0EEB8GF0W0NPCIHZX097"

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_create_submission_non_admin(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        submission_payload,
    ):
        """
        Test create Submission API
        """
        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # create test permissions
        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        await static_cache.refresh_values()

        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        j_resp = response.json()
        # assert
        assert response.status_code == status.HTTP_200_OK
        assert j_resp["id"]
        assert j_resp["active"]
        submission = await session.scalar(
            select(SubmissionObj).where(SubmissionObj.id == j_resp["id"])
        )
        assert submission
        assert submission.user_id is None
        assert submission.status == SubmissionObjStatusEnum.DRAFT
        assert submission.lei == "000012345678"

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_create_submission_on_non_active_view_raises_422(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        submission_payload,
    ):
        """
        Test create Submission API
        """
        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        table_view = await session.get(TableView, 1)
        table_view.active = False  # type: ignore
        await session.commit()
        # create test permissions
        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        await static_cache.refresh_values()

        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        j_resp = response.json()
        assert j_resp["detail"] == {
            "submission.table_view_id": (
                "Cannot accept a submission on a non-active view."
            )
        }

    # CREATE SUBMISSION MULTILANGUAGE

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_create_submission_latin_special(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        submission_payload,
    ):
        """
        Test create Submission API
        """
        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # create test permissions
        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # we have two fields so we split the string half and half
        submission_payload["values"]["s1_emissions_exclusion_dict"][0][
            "s1_emissions_exclusion_desc"
        ] = special_characters_latin[: len(special_characters_latin) // 2]
        submission_payload["values"]["s1_emissions_exclusion_dict"][1][
            "s1_emissions_exclusion_desc"
        ] = special_characters_latin[len(special_characters_latin) // 2 :]
        await static_cache.refresh_values()
        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        j_resp = response.json()
        # assert
        assert response.status_code == status.HTTP_200_OK
        assert j_resp["id"]

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_create_submission_other_special_first(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        submission_payload,
    ):
        """
        Test create Submission API
        """
        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # create test permissions
        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # take first 300 chars
        special_characters = special_characters_other[:300]
        # we have two fields so we split the string half and half
        submission_payload["values"]["s1_emissions_exclusion_dict"][0][
            "s1_emissions_exclusion_desc"
        ] = special_characters[: len(special_characters) // 2]
        submission_payload["values"]["s1_emissions_exclusion_dict"][1][
            "s1_emissions_exclusion_desc"
        ] = special_characters[len(special_characters) // 2 :]
        await static_cache.refresh_values()
        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        j_resp = response.json()
        # assert
        assert response.status_code == status.HTTP_200_OK
        assert j_resp["id"]

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_create_submission_other_special_second(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        submission_payload,
    ):
        """
        Test create Submission API
        """
        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # create test permissions
        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # take second 300 chars
        special_characters = special_characters_other[300:600]
        # we have two fields so we split the string half and half
        submission_payload["values"]["s1_emissions_exclusion_dict"][0][
            "s1_emissions_exclusion_desc"
        ] = special_characters[: len(special_characters) // 2]
        submission_payload["values"]["s1_emissions_exclusion_dict"][1][
            "s1_emissions_exclusion_desc"
        ] = special_characters[len(special_characters) // 2 :]
        await static_cache.refresh_values()
        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        j_resp = response.json()
        # assert
        assert response.status_code == status.HTTP_200_OK
        assert j_resp["id"]

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_create_submission_other_special_third(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        submission_payload,
    ):
        """
        Test create Submission API
        """
        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # create test permissions
        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # take last characters
        special_characters = special_characters_other[600:]
        # we have two fields so we split the string half and half
        submission_payload["values"]["s1_emissions_exclusion_dict"][0][
            "s1_emissions_exclusion_desc"
        ] = special_characters[: len(special_characters) // 2]
        submission_payload["values"]["s1_emissions_exclusion_dict"][1][
            "s1_emissions_exclusion_desc"
        ] = special_characters[len(special_characters) // 2 :]
        await static_cache.refresh_values()
        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        j_resp = response.json()
        # assert
        assert response.status_code == status.HTTP_200_OK
        assert j_resp["id"]

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_create_submission_invalid_text_constraint(
        self,
        client: AsyncClient,
        session: AsyncSession,
        submission_create_payload,
        static_cache: CoreMemoryCache,
    ):
        """
        Test create Submission API with invalid text data.
        """
        # arrange
        await create_test_form(data_dir / "form-create.json", session)
        submission_create_payload["values"]["data_model"] = "foo"
        # create test permissions
        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        await static_cache.refresh_values()
        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_create_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        j_resp = response.json()
        assert j_resp["reason"] == "Constraints validation error."
        assert j_resp["loc"] == "data_model"
        assert j_resp["value"] == "foo"
        assert "constraint_action" in j_resp

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_create_submission_invalid_int_constraint(
        self,
        client: AsyncClient,
        session: AsyncSession,
        submission_payload,
        static_cache: CoreMemoryCache,
    ):
        """
        Test create Submission API with invalid int data.
        """
        # arrange
        await create_test_form(data_dir / "form-create.json", session)
        submission_payload["values"]["reporting_year"] = 2300
        # create test permissions
        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        await static_cache.refresh_values()
        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        j_resp = response.json()
        assert j_resp["reason"] == "Constraints validation error."
        assert j_resp["loc"] == "reporting_year"
        assert j_resp["value"] == 2300
        assert "constraint_action" in j_resp

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_create_submission_invalid_datetime_constraint_min(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        submission_payload,
    ):
        """
        Test create Submission API with invalid date: below min.
        """
        # arrange
        await create_test_form(data_dir / "form-create.json", session)
        submission_payload["values"]["date_end_reporting_year"] = (
            "1995-09-05T00:00:00.000Z"
        )
        # create test permissions
        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        await static_cache.refresh_values()
        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert (
            response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        ), response.text
        j_resp = response.json()
        assert j_resp["reason"] == "Constraints validation error."
        assert j_resp["loc"] == "date_end_reporting_year"
        assert j_resp["value"] == "1995-09-05T00:00:00.000Z"
        assert "constraint_action" in j_resp

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_create_submission_invalid_date_constraint_max(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        submission_payload,
    ):
        """
        Test create Submission API with invalid date: above max.
        """
        # arrange
        await create_test_form(data_dir / "form-create.json", session)
        submission_payload["values"]["date_end_reporting_year"] = (
            "2300-05-06T00:00:00.000Z"
        )
        # create test permissions
        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        await static_cache.refresh_values()
        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        j_resp = response.json()
        assert j_resp["reason"] == "Constraints validation error."
        assert j_resp["loc"] == "date_end_reporting_year"
        assert j_resp["value"] == "2300-05-06T00:00:00.000Z"
        assert "constraint_action" in j_resp

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_create_submission_invalid_datetime_constraint_format(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        submission_payload,
    ):
        """
        Test create Submission API with invalid date format.
        """
        # arrange
        await create_test_form(data_dir / "form-create.json", session)
        submission_payload["values"]["date_end_reporting_year"] = (
            "27-06-2023T00:00:00.000Z"
        )
        # create test permissions
        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        await static_cache.refresh_values()
        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        j_resp = response.json()
        assert (
            j_resp["detail"]["date_end_reporting_year"]
            == "datetime 27-06-2023T00:00:00.000Z is not a valid isoformat string"
        )

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_create_submission_with_empty_values(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
    ):
        """
        Test create Submission API with empty values.
        """
        test_submission_no_values = {
            "nz_id": NZ_ID,
            "table_view_id": 1,
            "permissions_set_id": 1,
            "values": {},
        }
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # create test permissions
        await self.create_test_permissions(session)
        await static_cache.refresh_values()
        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json=test_submission_no_values,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()

        assert j_resp["user_id"] == 1
        assert j_resp["checked_out"] is True
        # TEST CASES FOR PERMISSION CHECK

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_create_submission_without_permission(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        submission_payload,
    ):
        """
        Test create Submission API without having the necessary permissions.
        """
        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # do not create test permissions but add role for API role auth
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        await static_cache.refresh_values()

        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        j_resp = response.json()
        assert (
            j_resp["detail"]["submission.permissions_set_id"]
            == "Invalid permission_set_id, select existent permission_set_id"
        )

    # TEST CASES FOR INVALID INPUT DATA

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_create_submission_with_invalid_table_view_id(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        submission_payload,
    ):
        """
        Test create Submission API with invalid table_view_id.
        """
        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        # create test permissions
        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        submission_payload["table_view_id"] = 9999  # non-existent id
        await static_cache.refresh_values()

        # act
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        "it should be handle and return 422 error but 404 returning instead"
        assert response.status_code == status.HTTP_404_NOT_FOUND
        j_resp = response.json()
        assert j_resp["detail"]["table_view_id"] == "Table view not found."


class TestSubmissionUpdate(AuthTest):
    """
    Test Submission Update API.
    """

    @pytest.mark.asyncio
    async def test_update_submission(
        self,
        client: AsyncClient,
        static_cache: CoreMemoryCache,
        session: AsyncSession,
        submission_payload,
    ):
        """
        Test update Submission API.
        """
        # create test permissions
        await self.create_test_permissions(session)
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)
        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        await static_cache.refresh_values()
        # send request
        values = submission_payload.pop("values")
        submission_payload["values"] = {}
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        # send request
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/1",
            json={"values": values},
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert len(j_resp["values"]) > 0

    @pytest.mark.asyncio
    async def test_update_submission_validate_number(
        self,
        client: AsyncClient,
        session: AsyncSession,
        submission_payload,
        static_cache: CoreMemoryCache,
    ):
        """
        Test create Submission with invalid number field.
        """
        # add admin permission to user
        # await self.add_admin_permissions_to_user(session)
        # arrange
        await create_test_form(data_dir / "form-create.json", session)

        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        await static_cache.refresh_values()
        # send request
        response = await client.post(
            url=BASE_ENDPOINT,
            json={**submission_payload, "values": {}},
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        # act
        values = submission_payload["values"]
        values["reporting_year"] = "2022"
        response = await client.patch(
            url=f"{BASE_ENDPOINT}/{j_resp['id']}",
            json={"values": values},
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        j_resp = response.json()
        assert (
            j_resp["detail"]["reporting_year"]
            == "Invalid data type str in reporting_year for comparison."
            " Must be an number."
        )

    @pytest.mark.asyncio
    async def test_update_submission_validate_text(
        self,
        client: AsyncClient,
        session: AsyncSession,
        submission_create_payload,
        static_cache: CoreMemoryCache,
    ):
        """
        Test create Submission with invalid text field.
        """
        # arrange
        await create_test_form(data_dir / "form-create.json", session)

        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        await static_cache.refresh_values()

        # send request
        response = await client.post(
            url=BASE_ENDPOINT,
            json={**submission_create_payload, "values": {}},
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        j_resp = response.json()
        # act

        values = submission_create_payload["values"]
        values["data_model"] = 1

        response = await client.patch(
            url=f"{BASE_ENDPOINT}/{j_resp['id']}",
            json={"values": values},
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        j_resp = response.json()

        assert (
            j_resp["detail"]["data_model"]
            == "Invalid data type int in data_model for comparison."
            " Must be a string"
        )

    @pytest.mark.asyncio
    async def test_update_submission_with_non_existent_permissions_set(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        submission_payload,
    ):
        """
        Test create Submission with non-existent permissions set.
        """
        submission_payload["permissions_set_id"] = 1
        # add admin permission to user
        await self.add_admin_permissions_to_user(session)

        # arrange
        await create_test_form(data_dir / SCHEMA_FILE_NAME, session)
        await static_cache.refresh_values()
        # send request
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        j_resp = response.json()
        assert (
            j_resp["detail"]["submission.permissions_set_id"]
            == "Invalid permission_set_id, select existent permission_set_id"
        )
        assert "detail" in j_resp

    @pytest.mark.asyncio
    async def test_update_submission_invalid_condition_constraint(
        self,
        client: AsyncClient,
        session: AsyncSession,
        submission_create_payload,
        static_cache: CoreMemoryCache,
    ):
        """
        Test create Submission with invalid condition constraint.
        """

        # arrange
        await create_test_form(data_dir / "form-create.json", session)

        # create test permissions
        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        await static_cache.refresh_values()

        async with session as _session:
            organizational_boundary = await session.scalar(
                select(ColumnDef).where(
                    ColumnDef.name == "org_boundary_approach"
                )
            )
            assert organizational_boundary
            org_bound = await session.scalar(
                select(ColumnView).where(
                    ColumnView.column_def_id == organizational_boundary.id
                )
            )
            assert org_bound
            new_constraint_values = [
                {
                    "code": "org_boundary_approach_visible",
                    "conditions": [
                        {
                            "target": "attribute",
                            "set": {"org_boundary_approach": {"eq": 1}},
                        },
                        {
                            "target": "attribute",
                            "set": {"org_boundary_approach": {"eq": 3}},
                        },
                    ],
                    "actions": [],
                }
            ]
            org_bound.constraint_value = new_constraint_values
            await _session.commit()

        submission_create_payload["values"]["org_boundary_approach"] = 2
        # send request
        response = await client.post(
            url=BASE_ENDPOINT,
            json=submission_create_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        j_resp = response.json()
        assert j_resp["reason"] == "Constraints validation error."
        assert j_resp["loc"] == "org_boundary_approach"
        assert j_resp["value"] == 2
        assert "constraint_condition" in j_resp


class TestSubmissionDelete(AuthTest):
    """
    Test rollback submission API.
    """

    data_dir: Path = settings.BASE_DIR.parent / "tests/data"

    @pytest.mark.asyncio
    async def test_delete_submission(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        submission_payload,
    ):
        """
        Test delete a revision and all related records API
        """
        # Arrange
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        # Create test permissions
        set_id: int = await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.DATA_PUBLISHER)
        # Create submission
        builder = SubmissionBuilder(
            cache=redis_client, session=session, static_cache=static_cache
        )
        submission = await builder.generate(
            table_view_id=1,
            nz_id=NZ_ID,
            permissions_set_id=set_id,
            tpl_file=SUBMISSION_SCHEMA_FILE_NAME,
            no_change=True,
        )
        await static_cache.refresh_values()
        # Set it checked out
        await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}/edit",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # Create revision
        await client.post(
            url=f"{BASE_ENDPOINT}/{submission.name}",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # Act: Delete the revision
        response = await client.delete(
            url=f"{BASE_ENDPOINT}/{submission.name}",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        # Assert
        assert response.status_code == status.HTTP_200_OK
        j_resp = response.json()
        assert j_resp == {"success": True, "deleted_revisions": 1}


class TestValidateAggregatedSubmissions(AuthTest):
    data_dir: Path = settings.BASE_DIR.parent / "tests/data"

    @pytest.mark.asyncio
    async def test_agregated_submission_no_diff(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        submission_payload,
    ):
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        # Create test permissions
        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.ADMIN)

        await static_cache.refresh_values()

        # Create submission
        await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        response = await client.get(
            url=f"{BASE_ENDPOINT}/validate-aggregated-submissions?start=0&limit=1",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "offset": 0,
            "limit": 1,
            "total": 1,
            "invalid_submissions": [],
        }

    @pytest.mark.skip(reason="Freezing")
    @pytest.mark.asyncio
    async def test_agregated_submission_exists_diff(
        self,
        static_cache: CoreMemoryCache,
        client: AsyncClient,
        session: AsyncSession,
        redis_client,
        submission_payload,
    ):
        await create_test_form(f"{self.data_dir}/{SCHEMA_FILE_NAME}", session)
        # Create test permissions
        await self.create_test_permissions(session)
        await self.add_role_to_user(session, AuthRole.ADMIN)
        # Create submission
        await static_cache.refresh_values()

        await client.post(
            url="/submissions",
            json=submission_payload,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        data = (
            (
                await session.execute(
                    select(AggregatedObjectView).where(
                        AggregatedObjectView.obj_id == 1
                    )
                )
            )
            .scalar()
            .data
        )

        data["data_source"] = "1111"

        await session.execute(
            update(AggregatedObjectView)
            .where(AggregatedObjectView.obj_id == 1)
            .values(data=json.dumps(data))
        )
        await session.commit()

        response = await client.get(
            url=f"{BASE_ENDPOINT}/validate-aggregated-submissions?start=0&limit=10",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "offset": 0,
            "limit": 10,
            "total": 1,
            "invalid_submissions": [
                {
                    "differences": [
                        [
                            "change",
                            "data_source",
                            ["CDP Climate Change 2015", "1111"],
                        ]
                    ],
                    "submission_id": 1,
                }
            ],
        }
