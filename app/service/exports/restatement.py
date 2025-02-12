import itertools
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AggregatedObjectView,
    ColumnDef,
    Restatement,
    SubmissionObj,
)
from app.db.redis import RedisClient
from app.db.types import NullTypeState
from app.routers.utils import get_choice_value
from app.schemas.restatements import (
    AttributePathsModel,
    RestatementAttributePrompt,
    RestatementGet,
    RestatementList,
    RestatementOriginal,
)
from app.schemas.submission import SubmissionGet
from app.service.core.cache import CoreMemoryCache
from app.service.core.loaders import SubmissionLoader
from app.service.exports.utils import (
    format_datetime_for_downloads,
    get_attribute_paths,
)
from app.service.utils import load_column_units


@dataclass
class RestatementExportManager:
    submissions: list[dict[str, Any]]
    session: AsyncSession
    cache: RedisClient
    static_cache: CoreMemoryCache
    restatements_emissions: list = field(default_factory=list)
    restatements_targets: list = field(default_factory=list)
    extract_targets: bool = False

    async def get_restatements_nz_id_mapping(
        self, ids
    ) -> dict[int, list[Restatement]]:
        relevant_submission_ids = (
            select(Restatement.obj_id)
            .where(Restatement.obj_id.in_(ids))
            .union(
                select(Restatement.group_id).where(Restatement.obj_id.in_(ids))
            )
        ).alias("relevant_ids")

        restatement_query = (
            select(
                Restatement,
                SubmissionObj,
            )
            .join(
                relevant_submission_ids,
                or_(
                    Restatement.obj_id == relevant_submission_ids.c.obj_id,
                    Restatement.group_id == relevant_submission_ids.c.obj_id,
                ),
            )
            .join(SubmissionObj, SubmissionObj.id == Restatement.obj_id)
            .order_by(SubmissionObj.revision)
            .group_by(SubmissionObj.nz_id, SubmissionObj.id, Restatement.id)
        )

        restatement_results = (
            await self.session.execute(restatement_query)
        ).all()

        result = {}
        for res in restatement_results:
            nz_id = res.SubmissionObj.nz_id
            if nz_id not in result:
                result[nz_id] = [res.Restatement]
            else:
                result[nz_id].append(res.Restatement)

        return result

    async def get_unit_value(self, field_name: str) -> str | None:
        unit_value = None
        if "emissions" in field_name:
            units = await load_column_units(
                field_name,
                self.session,
                self.static_cache,
            )
            if units:
                try:
                    unit_value = units[0]["actions"][0]["set"]["units"]
                except KeyError:
                    unit_value = None
        return unit_value

    @staticmethod
    def restatements_of_attr_by_year(
        submission_loader: SubmissionLoader,
        active_submission: dict,
        field_restatements: list[Restatement],
        field_value: AttributePathsModel,
    ) -> list[RestatementList]:
        active_submission_values = active_submission["values"]
        rest_by_year = [rest for rest in field_restatements]
        restated_value = submission_loader.return_value(
            field_value, active_submission_values
        )
        reporting_year = active_submission_values.get("reporting_year")
        return [
            RestatementList(
                reporting_year=reporting_year,
                reported_on=rest.reporting_datetime,
                value=restated_value,
                reason=rest.reason_for_restatement,
                disclosure_source=rest.data_source,
            )
            for rest in rest_by_year
        ]

    @staticmethod
    async def restatement_original(
        submission_loader: SubmissionLoader,
        original_submission: int,
        field_value: AttributePathsModel,
    ) -> RestatementOriginal:
        submission = await submission_loader.load(
            submission_id=original_submission,
            use_aggregate=True,
            db_only=False,
        )
        return RestatementOriginal(
            reporting_year=submission.values.get("reporting_year"),
            reported_on=submission.values.get(
                "reporting_datetime",
                submission.values.get("created_on"),
            ),
            value=submission_loader.return_value(
                field_value,
                submission.values,
            ),
            disclosure_source=submission.values.get("disclosure_source"),
        )

    @staticmethod
    def filter_restatements_by_field(
        restatements: list[Restatement], field_name: str
    ) -> list[Restatement]:
        field_restatements = [
            rest for rest in restatements if rest.attribute_name == field_name
        ]

        field_restatements.sort(key=lambda k: k.reporting_datetime.year)
        return field_restatements

    @staticmethod
    def restated_attr_paths_mapping(
        restatements: dict[int, list[Restatement]],
    ) -> dict[int, dict[str, AttributePathsModel]]:
        mapping = {}
        for nz_id, restatement_list in restatements.items():
            restated_fields_data_source = {
                rest.attribute_name: rest.data_source
                for rest in restatement_list
            }
            mapping[nz_id] = get_attribute_paths(restated_fields_data_source)
        return mapping

    def active_sub(
        self,
        field_restatements: list[Restatement],
        latest_submissions: list[dict | SubmissionGet] | None = None,
    ) -> dict | SubmissionGet | None:
        if not latest_submissions:
            latest_submissions = self.submissions
        active_sub_id = field_restatements[0].obj_id
        if isinstance(latest_submissions[0], dict):
            active_submission = next(
                (
                    sub
                    for sub in latest_submissions
                    if sub.get("id") == active_sub_id
                ),
                None,
            )
        else:
            active_submission = next(
                (sub for sub in latest_submissions if sub.id == active_sub_id),
                None,
            )
        return active_submission

    async def get_original_submissions(
        self,
        restated_attr_paths_lookup: dict[int, dict[str, AttributePathsModel]],
        restatements: dict[int, list[Restatement]],
    ) -> dict[int, dict[str, int | dict]]:
        mapping = {}
        for nz_id, rest_list in restatements.items():
            originals_map = {}
            attribute_paths = restated_attr_paths_lookup[nz_id]
            for field_name in attribute_paths.keys():
                field_restatements = self.filter_restatements_by_field(
                    rest_list, field_name
                )
                first_restatement = field_restatements[0]
                originals_map[field_name] = first_restatement.group_id

            mapping[nz_id] = originals_map
        obj_ids = list(
            set(
                itertools.chain.from_iterable(
                    originals_map.values()
                    for originals_map in mapping.values()
                )
            )
        )
        nz_ids = list(mapping.keys())

        stmt = (
            select(
                SubmissionObj.nz_id.label("nz_id"),
                Restatement.attribute_name.label("attribute_name"),
                AggregatedObjectView,
            )
            .join(
                AggregatedObjectView,
                AggregatedObjectView.obj_id == SubmissionObj.id,
            )
            .join(Restatement, Restatement.group_id == SubmissionObj.id)
            .where(SubmissionObj.nz_id.in_(nz_ids))
            .where(AggregatedObjectView.obj_id.in_(obj_ids))
        )
        stmt_result = (await self.session.execute(stmt)).all()

        return_mapping = {}
        for row in stmt_result:
            if row.nz_id not in return_mapping:
                return_mapping[row.nz_id] = {}

            return_mapping[row.nz_id][row.attribute_name] = (
                row.AggregatedObjectView.data
            )

        return return_mapping

    async def restatement_excel_export(
        self,
        restatement: RestatementList,
        field_name: str,
        field_desc: str,
        active_sub: dict,
        unit_value: str | None = None,
    ):
        last_updated = format_datetime_for_downloads(restatement.reported_on)
        data_model = active_sub.get("values", {}).get("data_model")
        field_value = restatement.value
        return {
            "Reporting Year": restatement.reporting_year,
            "Data Model": data_model,
            "Restated Field Name": field_name,
            "Restated Short Description": field_desc,
            "Reporting Date": last_updated,
            "Field Value": (
                field_value if field_value else NullTypeState.LONG_DASH.value
            ),
            "Field Units": (
                unit_value if unit_value else NullTypeState.DASH.value
            ),
            "Restatement Rationale": (
                restatement.reason
                if restatement.reason
                else NullTypeState.DASH.value
            ),
            "Source": restatement.disclosure_source,
        }

    async def process_field_name_and_desc(
        self, field_name: str, field_value: AttributePathsModel, prompt: str
    ):
        if choice_value := field_value.choice.value:
            dyn_unit = await get_choice_value(
                choice_value,
                self.session,
                self.static_cache,
            )
            if "scope_1" in field_name:
                gas_map = {
                    "CO₂": "co2",
                    "CH₄": "ch4",
                    "N₂O": "n2o",
                    "HFCs": "hfcs",
                    "PFCs": "pfcs",
                    "SF₆": "sf6",
                    "NF₃": "nf3",
                    "Other greenhouse gas": "other",
                }
                dyn_unit = gas_map.get(dyn_unit, None)
                field_name += f"_{dyn_unit.lower()}"
            elif "scope_3_ghgp" in field_name:
                category = f"c{choice_value % 100}"
                field_name = field_name.replace(
                    "ghgp",
                    (f"ghgp_{category}" if category != 16 else "ghgp_other"),
                )
            elif "scope_3_iso" in field_name:
                category = f"c{choice_value % 100}"
                field_name = field_name.replace(
                    "iso",
                    (f"iso_{category}" if category != 16 else "iso_other"),
                )
            pattern = r"\{.*?\}"
            prompt = re.sub(
                pattern,
                (dyn_unit.upper() if "scope_1" in field_name else dyn_unit),
                prompt,
            )
        return field_name, prompt

    async def fill_restatements_export_data(
        self,
        target_list: list,
        field_name: str,
        field_desc: str,
        active_sub: dict,
        response: RestatementGet,
        unit_value: str | None = None,
        extra: dict | None = None,
    ):
        extra = extra or {}
        for rest in response.restatements:
            excel_data = await self.restatement_excel_export(
                rest,
                field_name,
                field_desc,
                active_sub,
                unit_value,
            )
            target_list.append({**excel_data, **extra})

        original_excel_data = await self.restatement_excel_export(
            response.original,
            field_name,
            field_desc,
            active_sub,
            unit_value,
        )

        target_list.append({**original_excel_data, **extra})

    async def extract_target_data(
        self,
        field_value: AttributePathsModel,
        field_desc: str,
        active_sub: dict,
        response: RestatementGet,
        unit_value: str | None = None,
    ):
        active_submission_values = active_sub.get("values")
        sub_form = f"{field_value.form}_heritable"
        # determine prefix
        prefix = "int" if "int" in sub_form else "abs"

        # extract target details using the prefix
        # target_data = active_submission_values.get(f"target_{prefix}")
        # target_id = target_data[field_value.row_id].get(f"tgt_{prefix}_id")
        # target_name = target_data[field_value.row_id].get(f"tgt_{prefix}_name")
        # target_excel_data = {
        #     "tgt_abs_id": (target_id if prefix == "abs" else None),
        #     "tgt_int_id": (target_id if prefix == "int" else None),
        #     "tgt_abs_name": (target_name if prefix == "abs" else None),
        #     "tgt_int_name": (target_name if prefix == "int" else None),
        # }

        await self.fill_restatements_export_data(
            self.restatements_targets,
            field_value.attribute,
            field_desc,
            active_sub,
            response,
            unit_value,
            extra={},
        )

    async def extract_emissions_data(
        self,
        field_value: AttributePathsModel,
        field_desc: str,
        active_sub: dict,
        response: RestatementGet,
        unit_value: str | None = None,
    ):
        await self.fill_restatements_export_data(
            self.restatements_emissions,
            field_value.attribute,
            field_desc,
            active_sub,
            response,
            unit_value,
        )

    async def extract_restated_field(
        self,
        nz_id: int,
        field_name: str,
        field_value: AttributePathsModel,
        original_submissions: dict[int, dict],
        active_submission: dict,
        restatements: list[Restatement],
        constraint_views: dict,
        submission_loader: SubmissionLoader,
    ):
        column_defs = await self.static_cache.column_defs_by_name()
        column_data: ColumnDef = column_defs.get(field_value.attribute)
        prompt = column_data.prompts[0]
        original_submission_values = original_submissions[nz_id][field_name]
        original_submission_id = original_submission_values.get("id")
        field_restatements = self.filter_restatements_by_field(
            restatements, field_name
        )
        if isinstance(original_submissions, dict) and isinstance(
            original_submission_id, int
        ):
            restatement_original = await self.restatement_original(
                submission_loader=submission_loader,
                original_submission=original_submission_id,
                field_value=field_value,
            )
            restatements_of_attr_by_active_year = (
                self.restatements_of_attr_by_year(
                    submission_loader,
                    active_submission,
                    field_restatements,
                    field_value,
                )
            )
            response = RestatementGet(
                nz_id=nz_id,
                attribute=RestatementAttributePrompt(
                    name=field_name,
                    prompt=prompt.value,
                ),
                original=restatement_original,
                restatements=restatements_of_attr_by_active_year,
            )
            unit_value = await self.get_unit_value(field_name)
            desc = response.attribute.prompt
            field_name, desc = await self.process_field_name_and_desc(
                field_name, field_value, desc
            )
            constraint_view = constraint_views.get(field_value.attribute)
            if (
                constraint_view
                and (
                    "TARGET_MAIN" in constraint_view.constraint_view["view"]
                    or "TARGET_PROGRESS"
                    in constraint_view.constraint_view["view"]
                )
                and self.extract_targets
            ):
                await self.extract_target_data(
                    field_value,
                    desc,
                    active_submission,
                    response,
                    unit_value,
                )
            elif (
                constraint_view
                and "COMPANY_PROFILE"
                in constraint_view.constraint_view["view"]
            ):
                await self.extract_emissions_data(
                    field_value,
                    desc,
                    active_submission,
                    response,
                    unit_value,
                )
