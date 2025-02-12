"""Submission builder"""

import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from dateutil.relativedelta import relativedelta
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings
from app.db.models import (
    Choice,
    ColumnDef,
    ColumnView,
    Organization,
    SubmissionObj,
    TableDef,
    User,
)
from app.db.redis import RedisClient
from app.schemas.column_def import AttributeType
from app.schemas.enums import SICSSectorEnum, SubmissionObjStatusEnum
from app.schemas.submission import SubmissionCreate
from app.service.core.cache import CoreMemoryCache
from app.service.core.errors import SubmissionError
from app.service.core.managers import SubmissionManager
from app.service.core.types import ColumnDefsDataByName
from app.service.faker import Faker
from tests.constants import SUBMISSION_SCHEMA_FILE_NAME
from tests.routers.utils import NZ_ID

data_dir: Path = settings.BASE_DIR.parent / "tests" / "data"


# pylint: disable = not-callable
@dataclass
class SubmissionBuilder:
    """
    Submission builder class, provides utilities to generate and insert
    fake submissions in the dartrabase.
    """

    cache: RedisClient
    session: AsyncSession
    static_cache: CoreMemoryCache

    async def _get_choice_set(self, choice_set_id: int) -> list[Choice]:
        """
        Retrieves a Choice set from the DB.

        Args:
            choice_set_id (int): The ID of the Choice set.

        Raises:
            ValueError: Not found.

        Returns:
            list[Choice]: The set of choices.
        """
        if choice_set_id not in self.loaded_choice_sets:
            choice_set = list(
                (
                    await self.session.scalars(
                        select(Choice).where(Choice.set_id == choice_set_id)
                    )
                )
                .unique()
                .all()
            )
            if not choice_set:
                raise ValueError(f"Choice set not found: '{choice_set_id}'")
            self.loaded_choice_sets[choice_set_id] = choice_set

        return self.loaded_choice_sets[choice_set_id]

    async def _generate_text_data(self, column: ColumnDef) -> str:
        """
        Generates value for AttributeType.TEXT type columns.

        Args:
            column (ColumnDef): The column definition.

        Returns:
            str: A sample string.
        """
        # first retrieve the constraints, if any
        if column.id not in self.constraints:
            column_view: ColumnView = await self.session.scalar(
                select(ColumnView).where(ColumnView.column_def_id == column.id)
            )
            assert column_view
            self.constraints[column.id] = (
                {
                    v: vv
                    for c in column_view.constraint_value
                    for k in c["actions"]
                    for v, vv in k["set"].items()
                }
                if column_view.constraint_value
                else {}
            )

        text = self.fake.text(column.name, **self.constraints[column.id])

        return text

    async def _generate_number_data(
        self, column: ColumnDef, is_float: bool = False
    ) -> int | float:
        """
        Generates value for AttributeType.INT and AttributeType.FLOAT
        type columns.

        Args:
            column (ColumnDef): The column definition.

        Returns:
            Union[int, float]: A fake generated number.
        """
        # first retrieve the constraints, if any
        if column.id not in self.constraints:
            column_view = await self.session.scalar(
                select(ColumnView).where(ColumnView.column_def_id == column.id)
            )
            assert column_view
            self.constraints[column.id] = (
                {
                    v: vv
                    for c in column_view.constraint_value
                    for k in c["actions"]
                    for v, vv in k["set"].items()
                }
                if column_view.constraint_value
                else {}
            )

        number = self.fake.number(
            is_float=is_float, **self.constraints[column.id]
        )

        return number

    async def _generate_datetime_data(self, column: ColumnDef) -> str:
        """
        Generates value for AttributeType.DATETIME type columns.

        Args:
            column (ColumnDef): The column definition.

        Returns:
            datetime: A fake generated datetime.
        """
        # first retrieve the constraints, if any
        if column.id not in self.constraints:
            column_view = await self.session.scalar(
                select(ColumnView).where(ColumnView.column_def_id == column.id)
            )
            assert column_view
            self.constraints[column.id] = (
                {
                    v: (
                        datetime.fromisoformat(vv)
                        if vv != "{currentDate}"
                        else datetime.now()
                    )
                    for c in column_view.constraint_value
                    for k in c["actions"]
                    for v, vv in k["set"].items()
                    if v in ["min", "max"]
                }
                if column_view.constraint_value
                else {}
            )

        _datetime = self.fake.datetime(**self.constraints[column.id])

        return _datetime.isoformat()

    async def _generate_multiple_data(self, column: ColumnDef) -> list[int]:
        """
        Generates value for AttributeType.MULTIPLE type columns.

        Args:
            column (ColumnDef): The column definition.

        Returns:
            list[int]: A random length list of random Choice IDs from
                the column's choice set.
        """
        if column.choice_set_id not in self.loaded_choice_sets:
            self.loaded_choice_sets[
                column.choice_set_id
            ] = await self._get_choice_set(column.choice_set_id)
        # generate random length list of unique random choices IDs
        choices = random.sample(
            [
                choice.id
                for choice in self.loaded_choice_sets[column.choice_set_id]
            ],
            k=random.randint(
                1, len(self.loaded_choice_sets[column.choice_set_id])
            ),
        )

        return choices

    async def _generate_single_data(self, column: ColumnDef) -> list[int]:
        """
        Generates value for AttributeType.SINGLE type columns.

        Args:
            column (ColumnDef): The column definition.

        Returns:
            list[int]: All the Choice IDs from the column's choice set.
        """
        if column.choice_set_id not in self.loaded_choice_sets:
            self.loaded_choice_sets[
                column.choice_set_id
            ] = await self._get_choice_set(column.choice_set_id)

        return [
            choice.choice_id
            for choice in self.loaded_choice_sets[column.choice_set_id]
        ]

    async def _generate_data(
        self,
        tpl: dict[str, Any],
        columns: ColumnDefsDataByName,
        heritable: bool = False,
    ) -> dict[str, Any]:
        """
        Generate fake submissions data.

        Args:
            tpl (dict[str, Any]): The submission template.
            columns (ColumnDefsDataByName): All column definitions by name.
            heritable (bool, optional): Internal use. Whether the
                current form is an heritable. Defaults to False.

        Returns:
            dict[str, Any]: The modified template with new values.
        """
        for k, v in tpl.items():

            def generate():
                return bool(random.getrandbits(1))

            column = columns[k]
            if column.attribute_type == AttributeType.TEXT:
                if not heritable or heritable and generate():
                    tpl[k] = await self._generate_text_data(column)
                else:
                    tpl[k] = None
            elif column.attribute_type == AttributeType.DATETIME:
                tpl[k] = await self._generate_datetime_data(column)
            elif column.attribute_type == AttributeType.BOOL:
                tpl[k] = bool(random.getrandbits(1))
            elif column.attribute_type in [
                AttributeType.INT,
                AttributeType.FLOAT,
            ]:
                if not heritable or heritable and generate():
                    tpl[k] = await self._generate_number_data(
                        column,
                        is_float=column.attribute_type == AttributeType.FLOAT,
                    )
                else:
                    tpl[k] = None
            elif column.attribute_type == AttributeType.FORM:
                if not heritable or heritable and generate():
                    sub_form = []
                    if isinstance(v, list):
                        for row in v:
                            sub_form.append(
                                await self._generate_data(
                                    row, columns, heritable=True
                                )
                            )
                        tpl[k] = sub_form
                    if isinstance(v, dict):
                        tpl[k] = await self._generate_data(
                            v, columns, heritable=True
                        )
                else:
                    tpl[k] = None
            elif column.attribute_type == AttributeType.MULTIPLE:
                tpl[k] = await self._generate_multiple_data(column)
            elif column.attribute_type == AttributeType.SINGLE:
                result = await self._generate_single_data(column)
                tpl[k] = random.choice(result)
        return tpl

    async def generate(
        self,
        table_view_id: int,
        nz_id: int | None = None,
        permissions_set_id: int = 0,
        tpl_file: str = SUBMISSION_SCHEMA_FILE_NAME,
        no_change: bool = False,
    ) -> SubmissionObj:
        """
        Generate a submission with fake values, starting from the values
        of a submission saved to a file as template.

        Args:
            table_view_id (int): The table view ID of the submission/
            permissions_set_id (int, optional): An optional permission
                set. Defaults to 0.
            tpl_file (str, optional): The template file. Defaults to
                "nzdpu-v40-sub.json".

        Returns:
            SubmissionObj: _description_
        """
        await self.static_cache.refresh_values()
        tpl_file_path = data_dir / tpl_file
        with open(tpl_file_path, encoding="utf-8") as f:
            tpl = json.load(f)

        submission = SubmissionCreate(
            nz_id=tpl.get("organization_identifier") if not nz_id else nz_id,
            table_view_id=table_view_id,
            permissions_set_id=permissions_set_id,
            data_source="CDP Climate Change 2015",
            values={
                "total_s1_emissions_ghg": 1094881,
                "rationale_s1_emissions_non_disclose": "N/A",
                "s1_emissions_method": "s1_emissions_method",
                "disclose_s1_emissions_exclusion": "disclose_s1_emissions_exclusion",
                "disclose_s1_emissions_change_type": "disclose_s1_emissions_change_type",
                "s1_ch4_emissions": 23412,
                "s1_co2_emissions": 1234,
                "total_s2_lb_emissions_co2": -999999,
            },
            status=SubmissionObjStatusEnum.DRAFT,
        )

        self.loaded_choice_sets = {}
        self.constraints = {}
        self.fake = Faker()

        # load last submission to get last submitting user
        last_submission = await self.session.scalar(
            select(SubmissionObj).order_by(SubmissionObj.id.desc())
        )
        submission_manager = SubmissionManager(
            redis_cache=self.cache,
            core_cache=self.static_cache,
            session=self.session,
        )
        columns_by_name = await self.static_cache.column_defs_by_name()
        table_views = await self.static_cache.table_views()
        if no_change:  # leave template values
            submission.values = tpl
        else:
            new_values = await self._generate_data(tpl, columns_by_name)
            submission.values = new_values
        table_view = table_views[table_view_id]
        # load last user of a submission to avoid max recursion error
        if last_submission:
            last_user = await self.session.get(
                User, last_submission.submitted_by
            )
        else:
            last_user = await self.session.get(User, table_view.user_id)
        assert last_user
        organization = await self.session.get(
            Organization, last_user.organization_id
        )
        if not organization:
            submission.values["legal_entity_identifier"] = self.fake.lei()
        else:
            submission.values["legal_entity_identifier"] = organization.lei
        submission.values["disclosure_source"] = submission.data_source

        return await self._insert(
            submission_manager=submission_manager,
            table_def=table_view.table_def,
            submission=submission,
            submitted_by=last_user.id,
            columns=columns_by_name,
            tried_years=set(),
        )

    async def _insert(
        self,
        submission_manager: SubmissionManager,
        table_def: TableDef,
        submission: SubmissionCreate,
        submitted_by: int,
        columns: ColumnDefsDataByName,
        tried_years: set,
    ) -> SubmissionObj | None:
        """
        Tries to insert the new submission. Retries recursively until
        success, or new user creation.

        If checking a duplicate submission fails, tries with another
        year until all available years in the contraint are used, then
        tries with the next user. If there are no more users available,
        create a new one and exits (does not generate submission in this
        case).

        Args:
            submission_manager (SubmissionManager): The SubmissionManager.
            submission (SubmissionCreate): The submission to insert.
            submitted_by (int): The ID of the submitting user.
            columns (ColumnDefsDataByName): All column definitions by name.
            tried_years (list, optional): Internal use, the years of the
                dates tried to be inserted as value to
                "date_end_reporting_year. Defaults to [].

        Returns:
            SubmissionObj | None: The created submission, or None if a
                new user was created.
        """
        try:
            # check duplicate submission
            await submission_manager.check_duplicate_submission(
                submission, submission.nz_id
            )
            return await submission_manager.create(
                submission, table_def, submitted_by
            )
        except HTTPException as err:
            if err.detail not in [
                {"submission": SubmissionError.SUBMISSION_NO_DATE},
                {"submissions": SubmissionError.SUBMISSION_ALREADY_EXISTS},
            ]:
                raise err
            column = columns["date_end_reporting_year"]
            column_view: ColumnView = column.views[0]
            constraints = column_view.constraint_value
            if constraints:
                min_date = constraints[0]["actions"][0]["set"]["min"]
                min_date = datetime.fromisoformat(min_date)
                max_date = constraints[0]["actions"][0]["set"]["max"]
                if max_date == "{currentDate}":
                    max_date = datetime.now().replace(tzinfo=timezone.utc)
                else:
                    max_date = datetime.fromisoformat(max_date)
                available_years = relativedelta(max_date, min_date).years
                if len(tried_years) <= available_years:
                    print(
                        "Duplicate submission detected, changing year...",
                        end=" " * 30 + "\r",
                    )

                    async def get_new_date(column):
                        # change year
                        new_date = await self._generate_datetime_data(column)
                        new_year = datetime.fromisoformat(new_date).year
                        if new_year in tried_years:
                            return await get_new_date(column)
                        tried_years.add(new_year)
                        return new_date

                    new_date = await get_new_date(column)
                    submission.values["date_end_reporting_year"] = new_date
                    submission.values["reporting_year"] = (
                        datetime.fromisoformat(new_date).year
                    )
                    # retry insert
                    await self._insert(
                        submission_manager,
                        table_def,
                        submission,
                        submitted_by,
                        columns,
                        tried_years,
                    )
                else:
                    print(
                        "Duplicate submission detected, trying another user...",
                        end=" " * 30 + "\r",
                    )
                    try:
                        next_user_id = submitted_by + 1
                        next_org_lei = await self.session.scalar(
                            select(Organization.nz_id)
                            .join(
                                User, Organization.id == User.organization_id
                            )
                            .where(User.id == next_user_id)
                        )
                        submission.values["legal_entity_identifier"] = (
                            next_org_lei
                        )
                        await self._insert(
                            submission_manager,
                            table_def,
                            submission,
                            next_user_id,
                            columns,
                            set(),
                        )
                    except (IntegrityError, ProgrammingError) as e:
                        # user has all dates available, create new user and exit
                        await self.session.rollback()
                        print(
                            "Creating new organization...", end=" " * 30 + "\r"
                        )
                        organization = Organization(
                            lei=self.fake.lei(),
                            legal_name="testorg",
                            jurisdiction="US-MA",
                            sics_sector=SICSSectorEnum.INFRASTRUCTURE,
                            sics_sub_sector="subsector",
                            sics_industry="sics_industry",
                            nz_id=NZ_ID,
                        )
                        self.session.add(organization)
                        await self.session.commit()
                        print("Creating new user...", end=" " * 30 + "\r")
                        name = f"user {submitted_by + 1}"
                        password = str(uuid4()).split("-")[0]
                        user = User(
                            name=name,
                            password=password,
                            external_user_id="",
                            organization_id=organization.id,
                        )
                        self.session.add(user)
                        await self.session.commit()
                        print(
                            "Submission generation failed, creating a new"
                            f" user with {name=} and {password=}"
                        )

            else:
                raise
