from datetime import datetime
from typing import Any

import numpy as np
import orjson
import pandas as pd
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AttributePrompt,
    ColumnDef,
    ColumnView,
)
from app.db.types import EN_DASH, NullTypeState
from app.routers.utils import (
    get_choice_value,
    get_value_from_computed_units,
)
from app.schemas.restatements import AttributePathsModel
from app.service.core.cache import CoreMemoryCache
from app.service.utils import load_column_units
from app.utils import convert_keys_to_str


def get_scope_emissions_data(d, scope_name, single=False):
    """
    Retrieve fields for scope emissions worksheets
    """
    emissions = {}
    # get emissions for scope 1 emissions
    if scope_name == "scope_1_emissions":
        methodology = d.get("s1_emissions_method", None)
        change_type = d.get("s1_emissions_change_type", None)
        disclose_ghg_other = d.get(
            "disclose_s1_emissions_bd_ghg_other_bool", None
        )
        if methodology is None:
            methodology = ["N/A"]
        if change_type is None:
            change_type = ["N/A"]
        # convert True/False to Yes/No
        disclose_ghg_other = (
            "Yes"
            if disclose_ghg_other
            else "No"
            if disclose_ghg_other is not None
            else None
        )
        # create emissions data
        emissions = {
            k: d.get(k, None)
            for k in d
            if k
            in (
                "total_s1_emissions_ghg",
                "total_s1_emissions_co2",
                "rationale_s1_emissions_non_disclose",
                "rationale_s1_emissions_ghg_bd_non_disclose"
                "rationale_s1_emissions_ghg_bd_non_disclose_other"
                "explan_s1_ghg_not_equal_s1_total",
                "s1_emissions_method",
                "s1_emissions_change_desc",
            )
        }

        emissions["disclose_s1_emissions_bd_ghg_other_bool"] = (
            disclose_ghg_other
        )
        emissions["s1_emissions_change_type"] = change_type

        # check if download-table and remove this fields
        if not single:
            keys_to_remove = [
                "disclose_s1_emissions_bd_ghg_other_bool",
                "disclose_s1_emissions_exclusion",
            ]
            for key in keys_to_remove:
                emissions.pop(key, None)
    # get emissions for scope 2 market-based emissions
    elif scope_name == "scope_2_mb_emissions":
        methodology_mb = d.get("s2_mb_emissions_method", None)
        change_type_mb = d.get("s2_mb_emissions_change_type", None)
        if methodology_mb is None:
            methodology_mb = ["N/A"]
        if change_type_mb is None:
            change_type_mb = ["N/A"]

        emissions = {
            k: d.get(k, None)
            for k in d
            if k
            in (
                "total_s2_mb_emissions_ghg",
                "total_s2_mb_missions_co2",
                "rationale_s2_mb_emissions_non_disclose",
                "s2_mb_emissions_change_desc",
            )
        }
        emissions["s2_mb_emissions_method"] = methodology_mb
        emissions["s2_mb_emissions_change_type"] = change_type_mb
    # get emissions for scope 2 location-based emissions
    elif scope_name == "scope_2_lb_emissions":
        methodology_lb = d.get("s2_mb_emissions_method", None)
        change_type_lb = d.get("s2_mb_emissions_change_type", None)
        if methodology_lb is None:
            methodology_lb = ["N/A"]
        if change_type_lb is None:
            change_type_lb = ["N/A"]

        emissions = {
            k: d.get(k, None)
            for k in d
            if k
            in (
                "total_s2_lb_emissions_ghg",
                "total_s2_lb_missions_co2",
                "rationale_s2_lb_emissions_non_disclose",
                "s2_lb_emissions_change_desc",
            )
        }
        emissions["s2_lb_emissions_method"] = methodology_lb
        emissions["s2_lb_emissions_change_type"] = change_type_lb

    return emissions


def scope_emissions_generator(values, scope_fields: list):
    """
    Make new strucutre with scope fields set from full values
    """
    emissions = {k: values.get(k, None) for k in values if k in scope_fields}
    return emissions


def scope_emissions_formatter(
    d: dict,
    scope_name: str,
    scope_form: str = None,
    scope_category: str = None,
):
    """
    Retrieve fields for scope emissions worksheets
    """
    emissions = {}
    # get emissions for scope 1 emissions
    if scope_name == "s1_emissions":
        scope_fields_list = [
            "total_s1_emissions_ghg",
            "total_s1_emissions_co2",
            "rationale_s1_emissions_non_disclose",
            "s1_emissions_method",
            "disclose_s1_emissions_exclusion",
        ]
        emissions = scope_emissions_generator(d, scope_fields_list)
    elif scope_name == "s1_change_type":
        scope_fields_list = [
            "disclose_s1_emissions_change_type",
            "s1_emissions_change_type",
            "s1_emissions_change_desc",
        ]
        emissions = scope_emissions_generator(d, scope_fields_list)
    # get emissions for scope 1 ghg breakdown
    elif scope_name == "s1_ghg":
        scope_fields_list = [
            "rationale_s1_emissions_bd_ghg_non_disclose",
            "explan_s1_ghg_not_equal_s1_total",
            "s1_co2_emissions",
            "s1_co2_emissions_gwp_source",
            "s1_co2_emissions_gwp_time_horizon",
            "rationale_s1_co2_emissions_non_disclose",
            "s1_ch4_emissions",
            "s1_ch4_emissions_gwp_source",
            "s1_ch4_emissions_gwp_time_horizon",
            "rationale_s1_ch4_emissions_non_disclose",
            "s1_n2o_emissions",
            "s1_n2o_emissions_gwp_source",
            "s1_n2o_emissions_gwp_time_horizon",
            "rationale_s1_n2o_emissions_non_disclose",
            "s1_hfcs_emissions",
            "s1_hfcs_emissions_gwp_source",
            "s1_hfcs_emissions_gwp_time_horizon",
            "rationale_s1_hfcs_emissions_non_disclose",
            "s1_pfcs_emissions",
            "s1_pfcs_emissions_gwp_source",
            "s1_pfcs_emissions_gwp_time_horizon",
            "rationale_s1_pfcs_emissions_non_disclose",
            "s1_sf6_emissions",
            "s1_sf6_emissions_gwp_source",
            "s1_sf6_emissions_gwp_time_horizon",
            "rationale_s1_sf6_emissions_non_disclose",
            "s1_nf3_emissions",
            "s1_nf3_emissions_gwp_source",
            "s1_nf3_emissions_gwp_time_horizon",
            "rationale_s1_nf3_emissions_non_disclose",
        ]
        emissions = scope_emissions_generator(d, scope_fields_list)
    # get emissions for scope 2 market-based emissions
    elif scope_name == "s2_mb_emissions":
        scope_fields_list = [
            "total_s2_mb_emissions_ghg",
            "total_s2_mb_emissions_co2",
            "rationale_s2_mb_emissions_non_disclose",
            "s2_mb_emissions_method",
            "disclose_s2_mb_emissions_exclusion",
        ]
        emissions = scope_emissions_generator(d, scope_fields_list)
    elif scope_name == "s2_mb_change_type":
        scope_fields_list = [
            "disclose_s2_mb_emissions_change_type",
            "s2_mb_emissions_change_type",
            "s2_mb_emissions_change_desc",
        ]
        emissions = scope_emissions_generator(d, scope_fields_list)
    # get emissions for scope 2 location-based emissions
    elif scope_name == "s2_lb_emissions":
        scope_fields_list = [
            "total_s2_lb_emissions_ghg",
            "total_s2_lb_emissions_co2",
            "rationale_s2_lb_emissions_non_disclose",
            "s2_lb_emissions_method",
            "disclose_s2_lb_emissions_exclusion",
        ]
        emissions = scope_emissions_generator(d, scope_fields_list)
    elif scope_name == "s2_lb_change_type":
        scope_fields_list = [
            "disclose_s2_lb_emissions_change_type",
            "s2_lb_emissions_change_type",
            "s2_lb_emissions_change_desc",
        ]
        emissions = scope_emissions_generator(d, scope_fields_list)
    # get emissions for scope 3 ghg protocol
    elif scope_name == "s3_emissions":
        scope_fields_list = [
            "disclose_s3_emissions_bd_source",
            "total_s3_emissions_ghg",
            "total_s3_emissions_co2",
        ]
        emissions = scope_emissions_generator(d, scope_fields_list)
    elif scope_name == "s3_emissions_category":
        scope_fields_list = [
            f"s3_{scope_form}_{scope_category}_emissions_relevancy",
            f"s3_{scope_form}_{scope_category}_emissions_relevancy_desc",
            f"rationale_s3_{scope_form}_{scope_category}_emissions_non_disclose",
            f"total_s3_{scope_form}_{scope_category}_emissions_ghg",
            f"total_s3_{scope_form}_{scope_category}_emissions_co2",
        ]
        emissions = scope_emissions_generator(d, scope_fields_list)
    elif scope_name == "s3_emissions_category_exclusion":
        scope_fields_list = [
            f"disclose_s3_{scope_form}_{scope_category}_emissions_exclusion",
        ]
        emissions = scope_emissions_generator(d, scope_fields_list)
    elif scope_name == "s3_emissions_category_change_type":
        scope_fields_list = [
            f"disclose_s3_{scope_form}_{scope_category}_emissions_change_type",
            f"s3_{scope_form}_{scope_category}_emissions_change_type",
            f"s3_{scope_form}_{scope_category}_emissions_change_desc",
        ]
        emissions = scope_emissions_generator(d, scope_fields_list)
    elif scope_name == "s3_emissions_others":
        scope_fields_list = [
            "s3_ghgp_other_desc",
            "s3_ghgp_other_emissions_relevancy",
            "s3_ghgp_other_emissions_relevancy_desc",
            "total_s3_ghgp_other_emissions_ghg",
            "total_s3_ghgp_other_emissions_co2",
        ]
        emissions = scope_emissions_generator(d, scope_fields_list)

    return emissions


def financed_emissions_formatter(
    d: dict,
    fe_name: str,
    fe_form: str = None,
):
    """
    Retrieve fields for financed emissions sheet
    """
    emissions = {}
    # get emissions for scope 1 emissions
    if fe_name == "fe_emissions":
        scope_fields_list = [
            f"total_fin_emissions_{fe_form}_ghg",
            f"total_fin_emissions_{fe_form}_co2",
            f"rationale_fin_emissions_{fe_form}_non_disclose",
            f"total_coverage_{fe_form}_perc",
            f"fin_emissions_{fe_form}_exclusion_explan",
            f"fin_emissions_{fe_form}_currency",
            f"fin_emissions_{fe_form}_sectoral_classification",
        ]
        emissions = scope_emissions_generator(d, scope_fields_list)
    elif fe_name == "fe_change_type":
        scope_fields_list = [
            f"fin_emissions_{fe_form}_change_type",
            f"fin_emissions_{fe_form}_change_desc",
        ]
        emissions = scope_emissions_generator(d, scope_fields_list)

    return emissions


def format_datetime_for_downloads(old_date):
    """
    Format datetime to "%Y-%m-%d"
    """
    possible_formats = [
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ]
    for format_str in possible_formats:
        try:
            input_date = datetime.strptime(str(old_date), format_str)
            old_date = input_date.strftime("%Y-%m-%d")
            return old_date
        except ValueError:
            pass
    return None


async def format_special_value(
    session: AsyncSession, static_cache: CoreMemoryCache, value: any
):
    if value not in NullTypeState.values():
        val_format = ""
        for val in value:
            if isinstance(val, int):
                val = await get_choice_value(
                    val,
                    session,
                    static_cache,
                )
            val_format += f"{val},"
        value = val_format
    return value


async def get_prompt_from_key(
    session: AsyncSession, key: str, values: dict[str, Any]
) -> str:
    """
    Get attribute prompt field from the key
    """
    is_prompt = key.endswith("_prompt")
    prompt = ""
    try:
        prompt = values[key + "_prompt" if not is_prompt else key]
    except KeyError:
        if not is_prompt:
            col_prompt = await session.scalar(
                select(AttributePrompt.value)
                .join(
                    ColumnDef,
                    ColumnDef.id == AttributePrompt.column_def_id,
                )
                .where(ColumnDef.name == key)
            )
            if col_prompt:
                prompt = col_prompt

    return prompt


def clean_companies_targets_int_data(target_key, data, keys_to_remove):
    """
    Clean targets physical and economic lists
    """
    if target_key in data and isinstance(data[target_key], list):
        for item in data[target_key]:
            if isinstance(item, dict):
                for key in keys_to_remove:
                    item.pop(key, None)


def remove_keys_form_fe(data, keys_to_remove):
    """
    Return financed emissions with not keys to remove
    """
    if isinstance(data, dict):
        return {
            k: remove_keys_form_fe(v, keys_to_remove)
            for k, v in data.items()
            if k not in keys_to_remove
        }
    if isinstance(data, list):
        return [remove_keys_form_fe(v, keys_to_remove) for v in data]
    return data


def get_financed_emissions_data(d, scope_name):
    """
    Retrieve fields for scope emissions worksheets
    """
    emissions = {
        f"fn_{scope_name}_total_emissions_ghg_sum": d.get(
            f"fn_{scope_name}_total_emissions_ghg_sum", None
        ),
        f"fn_{scope_name}_total_emissions_co2_sum": d.get(
            f"fn_{scope_name}_total_emissions_co2_sum", None
        ),
        f"rationale_fn_{scope_name}_non_disclose": d.get(
            f"rationale_fn_{scope_name}_non_disclose", None
        ),
        f"{scope_name}_coverage_total_perc": d.get(
            f"{scope_name}_coverage_total_perc", None
        ),
        f"fn_{scope_name}_exclusions": d.get(
            f"fn_{scope_name}_exclusions", None
        ),
        f"currency_fn_{scope_name}": d.get(f"currency_fn_{scope_name}", None),
        f"fn_{scope_name}_sector_classification": d.get(
            f"fn_{scope_name}_sector_classification", None
        ),
        f"fn_{scope_name}_sector_classification_other": d.get(
            f"fn_{scope_name}_sector_classification_other", None
        ),
        f"fn_{scope_name}_change_type": d.get(
            f"fn_{scope_name}_change_type", None
        ),
        f"fn_{scope_name}_change_description": d.get(
            f"fn_{scope_name}_change_description", None
        ),
    }
    return emissions


async def remove_keys_from_dict(json_dict):
    """
    Remove keys from financed emissions data
    """
    keys_to_remove = [
        "fn_aum_coverage_sector",
        "sector_axis_data_quality",
        "fn_gross_exp_coverage_sector",
        "sector_axis_gross_sector_appended",
        "gr_int_ec_fn_gross_exp_int_sector",
        "gr_dq_fn_gross_exp_sector",
        "int_ph_fn_aum_int_sector",
        "sector_axis_aum_sector_appended",
    ]
    if isinstance(json_dict, dict):
        for key in list(json_dict.keys()):
            if key in keys_to_remove:
                del json_dict[key]
            else:
                await remove_keys_from_dict(json_dict[key])
    elif isinstance(json_dict, list):
        for item in json_dict:
            await remove_keys_from_dict(item)

    return json_dict


async def export_scope_3_companies(data: dict):
    """
    Return export from scope 3
    """
    scope_3_ghg = {
        "scope_3_breakdown_source": data.pop("scope_3_breakdown_source", None),
        "total_scope_3_emissions_ghg": data.pop(
            "total_scope_3_emissions_ghg", None
        ),
        "total_scope_3_emissions_co2": data.pop(
            "total_scope_3_emissions_co2", None
        ),
    }
    main = {}
    methodology = {}
    exclusion = {}
    change = {}
    for key, value in data.items():
        if "methodology" in key:
            methodology[key] = value
        elif "exclusion" in key:
            exclusion[key] = value
        elif "change" in key:
            change[key] = value
        else:
            main[key] = value

    categories = set()
    for key in data.keys():
        for part in key.split("ghgp_"):
            if part.startswith("c") and part[1:3].isdigit():
                categories.add(part[:3])
            elif part.startswith("c") and part[1:2].isdigit():
                categories.add(part[:2])
            elif part.startswith("other"):
                categories.add(part[:5])
    scope_3_category = {}
    for cat in categories:
        for k, v in main.items():
            if cat == "other":
                if f"{cat}_" in k or k.endswith("other"):
                    if f"scope_3_ghg_{cat}_main" not in scope_3_category:
                        scope_3_category[f"scope_3_ghg_{cat}_main"] = {}
                    scope_3_category[f"scope_3_ghg_{cat}_main"][k] = v
            else:
                if f"{cat}_" in k:
                    if f"scope_3_ghg_{cat}_main" not in scope_3_category:
                        scope_3_category[f"scope_3_ghg_{cat}_main"] = {}
                    scope_3_category[f"scope_3_ghg_{cat}_main"][k] = v
        for k, v in methodology.items():
            if f"{cat}_" in k:
                if f"scope_3_ghg_{cat}_methodology" not in scope_3_category:
                    scope_3_category[f"scope_3_ghg_{cat}_methodology"] = {}
                scope_3_category[f"scope_3_ghg_{cat}_methodology"][k] = v
        for k, v in exclusion.items():
            if f"{cat}_" in k:
                if f"scope_3_ghg_{cat}_exclusion" not in scope_3_category:
                    scope_3_category[f"scope_3_ghg_{cat}_exclusion"] = {}
                scope_3_category[f"scope_3_ghg_{cat}_exclusion"][k] = v
        for k, v in change.items():
            if f"{cat}_" in k:
                if f"scope_3_ghg_{cat}_change" not in scope_3_category:
                    scope_3_category[f"scope_3_ghg_{cat}_change"] = {}
                scope_3_category[f"scope_3_ghg_{cat}_change"][k] = v

    return scope_3_ghg, scope_3_category


async def update_dataframe(
    df,
    data,
    desc,
    source_data,
    reported_data,
    units_data,
    source,
    last_updated,
    reporting_year,
    sheet,
    session,
    static_cache,
    restated=False,
):
    """
    Return new dataframe
    """
    source = (
        await get_choice_value(source, session, static_cache)
        if type(source) is int
        else source
    )
    if sheet in ["scope", "fe"]:
        if desc:
            new_headers = [
                key
                for key in desc.keys()
                if key not in df["Field Name"].tolist()
            ]
            if new_headers:
                new_df = pd.DataFrame(
                    {
                        "Field Name": [key for key in new_headers],
                        "Short Description": [
                            desc[key] for key in new_headers
                        ],
                        "Units": [units_data[key] for key in new_headers],
                    }
                )
                df = pd.concat([df, new_df], ignore_index=True, axis=0)
            df.loc[df["Units"].isna() | (df["Units"] == ""), "Units"] = df[
                "Field Name"
            ].map(units_data)
    elif sheet == "metadata":
        if df.empty:
            df = pd.DataFrame(
                {
                    "Field Name": list(desc.keys()),
                    "Short Description": list(desc.values()),
                }
            )
    # add columns for the specific reporting year
    if sheet in ["scope", "fe"]:
        df[f"Value_{reporting_year}"] = df["Field Name"].map(data)
        df[f"Source_{reporting_year}"] = (
            df["Field Name"].map(source_data) if source_data else None
        )
        df[f"Last Updated_{reporting_year}"] = (
            df["Field Name"].map(reported_data) if reported_data else None
        )
        if restated:
            if source_data:
                for key in df["Field Name"]:
                    source_value = source_data.get(key)
                    if source_value != source and source_value not in [
                        "-",
                        EN_DASH,
                        None,
                    ]:
                        df.loc[
                            df["Field Name"] == key,
                            f"Restated_{reporting_year}",
                        ] = "Yes"
    if sheet == "metadata":
        metadata_source_map = {
            "legal_entity_identifier": source,
            "legal_name": "GLEIF",
            "jurisdiction": "GLEIF, mapped by NZDPU to UNFCCC GCAP's jurisdiction list",
            "sics_sector": "SICS",
            "sics_sub_sector": "SICS",
            "sics_industry": "SICS",
            "data_model": "NZDPU",
            "reporting_year": source,
            "date_start_reporting_year": source,
            "date_end_reporting_year": source,
            "org_boundary_approach": source,
        }
        df[f"Value_{reporting_year}"] = df["Field Name"].map(data)
        df[f"Source_{reporting_year}"] = df["Field Name"].map(
            metadata_source_map
        )
        df[f"Last Updated_{reporting_year}"] = last_updated
    else:
        if sheet not in ["scope", "targets", "fe"]:
            df[f"Source_{reporting_year}"] = np.where(
                df[f"Value_{reporting_year}"].notna(), source, None
            )
            df[f"Last Updated_{reporting_year}"] = np.where(
                df[f"Value_{reporting_year}"].notna(), last_updated, None
            )
        elif sheet == "targets":
            if restated:
                if source_data:
                    for key in df["Field Name"]:
                        source_value = source_data.get(key)
                        if source_value != source and source_value not in [
                            "-",
                            EN_DASH,
                            None,
                        ]:
                            df.loc[
                                df["Field Name"] == key,
                                f"Restated_{reporting_year}",
                            ] = "Yes"
    # -> pop out restated field for now
    # df[f"Restated_{reporting_year}"] = None
    return df


async def return_unit_from_field(
    field, session, static_cache, sheet, computed_units=None
):
    """
    Return unit from the provided field
    """
    conditions = []
    if sheet == "scope":
        conditions = [
            (field.startswith("total_s1"), field),
            (field.startswith("s1_") and field.endswith("emissions"), field),
            (
                field.startswith("total_s3")
                and field.endswith("emissions_ghg"),
                field,
            ),
            (
                field.startswith("total_s3")
                and field.endswith("emissions_co2"),
                field,
            ),
        ]
    elif sheet == "financed":
        unit = await get_value_from_computed_units(field, computed_units)
        # check if unit is None
        if unit is None:
            units_full = await load_column_units(field, session, static_cache)
            unit = (
                units_full[0]["actions"][0]["set"]["units"]
                if isinstance(units_full, (dict, list))
                else ""
            )
            if "{" in unit:
                unit = None
        return unit
    for condition, new_field in conditions:
        if condition:
            unit = await load_column_units(new_field, session, static_cache)
            return (
                unit[0]["actions"][0]["set"]["units"]
                if isinstance(unit, (dict, list))
                else ""
            )


async def get_attribute_prompt_from_path(
    attribute_path: AttributePathsModel,
    static_cache: CoreMemoryCache,
) -> AttributePrompt:
    columns = (await static_cache.column_defs_by_name()).values()
    for col in columns:
        if col.name == attribute_path.attribute:
            return col.prompts[0]

    raise HTTPException(
        status_code=404,
        detail={
            "attribute": (
                f"Column definition for '{attribute_path.attribute}' in"
                " table_def could not be found."
            )
        },
    )


def get_computed_unit_from_field(d, key):
    """
    Return unit from the provided field in computed units
    """
    if isinstance(d, dict):
        if key in d:
            return d[key]
        for value in d.values():
            result = get_computed_unit_from_field(value, key)
            if result is not None:
                return result
    elif isinstance(d, list):
        for item in d:
            result = get_computed_unit_from_field(item, key)
            if result is not None:
                return result
    return None


async def get_column_names_financed_emissions(fe_name, all_fields=True):
    """
    Return dict of column names from provided financed emissions name
    """
    common_fields = [
        "legal_entity_identifier",
        "company_name",
        "data_model",
        "reporting_year",
        "org_boundary_approach",
    ]
    column_names = {
        "fe_overview_headers": [
            f"fn_{fe_name}_total_emissions_ghg_sum",
            f"fn_{fe_name}_total_emissions_co2_sum",
            f"rationale_fn_{fe_name}_non_disclose",
            f"{fe_name}_coverage_total_perc",
            f"fn_{fe_name}_exclusions",
            f"currency_fn_{fe_name}",
            f"fn_{fe_name}_sector_classification",
            f"fn_{fe_name}_sector_classification_other",
            f"fn_{fe_name}_change_type",
            f"fn_{fe_name}_change_description",
            f"disclose_fn_{fe_name}_abs_yn",
            f"disclose_fn_{fe_name}_int_yn",
            f"disclose_fn_{fe_name}_data_quality_yn",
        ],
        "fn_coverage_headers": [
            "org_boundary_approach",
            f"fn_{fe_name}_asset_class",
            f"fn_{fe_name}_sector",
            f"fn_{fe_name}_coverage_scope",
            f"fn_{fe_name}_coverage_s3_cat",
            f"fn_{fe_name}_scope_1_emissions_ghg",
            f"fn_{fe_name}_scope_1_emissions_co2",
            f"fn_{fe_name}_coverage_ghg_s1",
            f"{fe_name}_coverage_s1",
            f"{fe_name}_coverage_s1_usd",
            f"fn_{fe_name}_scope_2_emissions_ghg",
            f"fn_{fe_name}_scope_2_emissions_co2",
            f"fn_{fe_name}_coverage_ghg_s2",
            f"{fe_name}_coverage_s2",
            f"{fe_name}_coverage_s2_usd",
            f"fn_{fe_name}_scope_1_and_2_emissions_ghg",
            f"fn_{fe_name}_scope_1_and_2_emissions_co2",
            f"fn_{fe_name}_coverage_ghg_s1s2",
            f"{fe_name}_coverage_s1s2",
            f"{fe_name}_coverage_s1s2_usd",
            f"fn_{fe_name}_scope_3_emissions_ghg",
            f"fn_{fe_name}_scope_3_emissions_co2",
            f"fn_{fe_name}_coverage_ghg_s3",
            f"{fe_name}_coverage_s3",
            f"{fe_name}_coverage_s3_usd",
            f"fn_{fe_name}_total_emissions_ghg",
            f"fn_{fe_name}_total_emissions_co2",
            f"fn_{fe_name}_coverage_ghg_total",
            f"{fe_name}_coverage_total",
            f"{fe_name}_coverage_total_usd",
            f"fn_{fe_name}_methodology",
            f"fn_{fe_name}_methodology_underlying",
        ],
        "fn_int_headers": [
            f"fn_{fe_name}_intensity_type",
            f"fn_{fe_name}_phys_int_description",
            f"fn_{fe_name}_phys_int_asset_class",
            f"fn_{fe_name}_phys_int_sector",
            f"fn_{fe_name}_phys_int_coverage_scope",
            f"fn_{fe_name}_phys_int_coverage_s3_cat",
            f"fn_{fe_name}_emissions_physical_intensity",
            f"fn_{fe_name}_units_phys_int_numerator",
            f"fn_{fe_name}_units_phys_int_denom",
            f"fn_{fe_name}_units_phys_int_denom_other",
            f"fn_{fe_name}_phys_int_coverage_ghg",
            f"fn_{fe_name}_phys_int_methodology",
            f"fn_{fe_name}_phys_int_methodology_underlying",
            f"fn_{fe_name}_econ_int_description",
            f"fn_{fe_name}_econ_int_asset_class",
            f"fn_{fe_name}_econ_int_sector",
            f"fn_{fe_name}_econ_int_coverage_scope",
            f"fn_{fe_name}_econ_int_coverage_s3_cat",
            f"fn_{fe_name}_emissions_economic_intensity",
            f"fn_{fe_name}_emissions_economic_intensity_usd",
            f"fn_{fe_name}_econ_int_coverage_s3_cat",
            f"fn_{fe_name}_emissions_economic_intensity",
            f"fn_{fe_name}_emissions_economic_intensity_usd",
            f"fn_{fe_name}_units_int_numerator",
            f"fn_{fe_name}_units_econ_int_denom",
            f"fn_{fe_name}_units_econ_int_denom_other",
            f"fn_{fe_name}_econ_int_coverage_ghg",
            f"fn_{fe_name}_econ_int_coverage_ghg",
            f"fn_{fe_name}_econ_int_methodology",
            f"fn_{fe_name}_econ_int_methodology_underlying",
        ],
        "fn_dq_headers": [
            f"fn_{fe_name}_data_quality_asset_class",
            f"fn_{fe_name}_data_quality_sector",
            f"fn_{fe_name}_perc_reported",
            f"fn_{fe_name}_pcaf_data_quality_score_s1",
            f"fn_{fe_name}_pcaf_data_quality_score_s2",
            f"fn_{fe_name}_pcaf_data_quality_score_s1s2",
            f"fn_{fe_name}_pcaf_data_quality_score_s3",
            f"fn_{fe_name}_pcaf_data_quality_score_total",
        ],
    }
    if all_fields:
        for key in column_names:
            column_names[key] = common_fields + column_names[key]

    return column_names


async def load_choice_from_root_data(
    root_data: dict, session: AsyncSession, static_cache
):
    """
    Return dict with choice values
    """
    items = {}
    for k, v in root_data.items():
        v = (
            await get_choice_value(v, session, static_cache)
            if type(v) is int
            else v
        )
        items[k] = v

    return items


async def format_value_download_all(
    value, sample, value_index, data_source_list, session, static_cache
):
    """
    Format source and last_updated value for download-all
    sample in Data Explorer
    """
    sample_index_value = None
    # check if source=0 or last_updated=1
    if value_index == 0 and isinstance(value, tuple):
        sample_index_value = await get_choice_value(
            value[value_index], session, static_cache
        )
    elif value_index == 1 and isinstance(value, tuple):
        sample_index_value = format_datetime_for_downloads(value[value_index])
    # render if value is source, restated source or blank
    value = (
        sample_index_value
        if isinstance(value, tuple) and value[0] in data_source_list
        else sample
        if value is not None
        else EN_DASH
    )
    return value


def align_df_data_and_desc(data_dict, column_names_dict):
    """
    Align dataframe data and desc to have same keys and values
    """
    aligned_dict = orjson.loads(orjson.dumps(convert_keys_to_str(data_dict)))
    for key in column_names_dict:
        if key not in aligned_dict:
            aligned_dict[key] = None
    return aligned_dict


async def format_restatements(data, session, static_cache):
    """
    Format restatements from original path e.g. <form>.<index>.<attribute>
    """
    items = {}
    for d in data:
        for key, value in d.items():
            keys = key.split(".")
            formatted_key = ""
            for k in keys:
                if ":" in k:
                    k = k.split(":")[-1].strip("}")
                formatted_key += f"{k}."
            value = await get_choice_value(value, session, static_cache)
            items[formatted_key[:-1]] = value
    return items


async def generate_data_source_from_restatements(
    data: dict[str, Any],
    update_dict: dict,
    keys: dict,
    value=None,
    is_recursive=False,
) -> dict[str, Any]:
    """
    Generate submission data to data_source where restatement value is changed
    """
    if not is_recursive:
        for key, value in update_dict.items():
            keys = key.split(".")
            await generate_data_source_from_restatements(
                data, {}, keys, value, True
            )
        return data
    if len(keys) == 1:
        data[keys[0]] = value
    else:
        if not keys[1].isdigit():
            data[keys[0]] = data.get(keys[0], {})
            await generate_data_source_from_restatements(
                data[keys[0]], {}, keys[1:], value, True
            )
        else:
            index = int(keys[1])
            data[keys[0]] = data.get(keys[0], [])
            while len(data[keys[0]]) <= index:
                data[keys[0]].append({})
            await generate_data_source_from_restatements(
                data[keys[0]][index], {}, keys[2:], value, True
            )
    return data


def clean_targets_int_data(target_key, data, keys_to_remove):
    """
    Clean targets physical and economic lists
    """
    if target_key in data and isinstance(data[target_key], list):
        for item in data[target_key]:
            if isinstance(item, dict):
                for key in keys_to_remove:
                    item.pop(key, None)


async def extract_data_from_fe(
    d: dict[str, Any],
    keys: list[str],
    session: AsyncSession,
    static_cache: CoreMemoryCache,
    source=None,
    last_updated=None,
    data_source_list=None,
):
    """
    Extract data to new dict with list of keys.
    """
    new_dict = {}
    description = {}
    keys_to_remove = ["id", "obj_id", "value_id"]
    for key in keys_to_remove:
        d.pop(key, None)
    for key in keys:
        if key.endswith("_prompt"):
            continue
        # Extract description for the key
        desc = await get_prompt_from_key(session=session, key=key, values=d)
        if key in d:
            if isinstance(d[key], list):
                counter = 1
                for v in d[key]:
                    if isinstance(v, int):
                        if source:
                            if last_updated:
                                # format last_updated value
                                v = await format_value_download_all(
                                    value=v,
                                    sample=last_updated,
                                    value_index=1,
                                    session=session,
                                    static_cache=static_cache,
                                    data_source_list=data_source_list,
                                )
                            else:
                                # format source value
                                v = await format_value_download_all(
                                    value=v,
                                    sample=source,
                                    value_index=0,
                                    session=session,
                                    static_cache=static_cache,
                                    data_source_list=data_source_list,
                                )
                        else:
                            v = await get_choice_value(
                                v, session, static_cache
                            )
                    new_key = f"{key}_{counter}"

                    if source:
                        if last_updated:
                            # format last_updated value
                            v = await format_value_download_all(
                                value=v,
                                sample=last_updated,
                                value_index=1,
                                session=session,
                                static_cache=static_cache,
                                data_source_list=data_source_list,
                            )
                        else:
                            # format source value
                            v = await format_value_download_all(
                                value=v,
                                sample=source,
                                value_index=0,
                                static_cache=static_cache,
                                session=session,
                                data_source_list=data_source_list,
                            )
                    new_dict[new_key] = str(v)
                    description[new_key] = desc
                    if key.endswith("ghg_sum") or key.endswith("co2_sum"):
                        k_unit = new_key + "_units"
                        v_unit = await load_column_units(
                            key, session, static_cache
                        )
                        new_dict[k_unit] = (
                            v_unit[0]["actions"][0]["set"]["units"]
                            if isinstance(v_unit, (dict, list))
                            else v_unit
                        )
                        description[k_unit] = desc + " units" if desc else desc
                    counter += 1
            else:
                if isinstance(d[key], int):
                    d[key] = await get_choice_value(
                        d[key], session, static_cache
                    )
                if source:
                    if last_updated:
                        # format last_updated value
                        d[key] = await format_value_download_all(
                            value=d[key],
                            sample=last_updated,
                            value_index=1,
                            session=session,
                            static_cache=static_cache,
                            data_source_list=data_source_list,
                        )
                    else:
                        # format source value
                        d[key] = await format_value_download_all(
                            value=d[key],
                            sample=source,
                            value_index=0,
                            session=session,
                            static_cache=static_cache,
                            data_source_list=data_source_list,
                        )
                new_dict[key] = str(d[key])
                description[key] = desc
                if key.endswith("ghg_sum") or key.endswith("co2_sum"):
                    k_unit = key + "_units"
                    v_unit = await load_column_units(
                        key, session, static_cache
                    )
                    new_dict[k_unit] = (
                        v_unit[0]["actions"][0]["set"]["units"]
                        if isinstance(v_unit, (dict, list))
                        else v_unit
                    )
                    description[k_unit] = desc + " units" if desc else desc

    return new_dict, description


def remove_fields_from_form(values: list, fields: list):
    """
    Remove fields from values and format new dict
    """
    return [
        {k: v for k, v in item.items() if k not in fields}
        for item in values
        if values not in (*NullTypeState.values(), None)
    ]


def get_attribute_paths(
    restated_fields_data_source: dict[str, int],
) -> dict[str, AttributePathsModel]:
    def allowed_attr_name(v: AttributePathsModel) -> bool:
        return v.attribute not in [
            "scope_1_greenhouse_gas",
            "scope_1_greenhouse_gas_other",
            "rationale_s1_ghg_non_disclose",
            "rationale_s1_ghg_non_disclose_other",
        ]

    def allowed_restated_key(v: str):
        return allowed_attr_name(AttributePathsModel.unpack_field_path(v))

    keys = list(
        filter(allowed_restated_key, restated_fields_data_source.keys())
    )
    values = [AttributePathsModel.unpack_field_path(v) for v in keys]

    return dict(zip(keys, values))


async def get_constraint_views(
    session: AsyncSession,
    attribute_paths: dict[str, AttributePathsModel],
) -> dict[str, Any]:
    org_attribute = [attr.attribute for attr in attribute_paths.values()]
    constraints_result = await session.execute(
        select(ColumnDef.name.label("name"), ColumnView)
        .join(ColumnDef, ColumnDef.id == ColumnView.column_def_id)
        .filter(ColumnDef.name.in_(org_attribute))
    )
    constraints = constraints_result.all()
    return {c.name: c.ColumnView for c in constraints}


def combine_units_into_one_list(root_list: list, sub_list: list):
    """
    Combine root and sub list into one list of dicts (used for targets units)
    """
    for i in range(min(len(root_list), len(sub_list))):
        root_list[i].update(sub_list[i])
    return root_list


def merge_list_data_frames(old_list: list, new_list: list):
    """Merge 2 list of data frames

    Merge 2 list of data frames by comparing their length, keep the data frame that has the longes length

    Returns:
        list: list of data frames with the longest lengths
    """
    list_to_return = []

    for i in range(0, len(new_list)):
        old_item = old_list[i]
        new_item = new_list[i]

        if len(old_item) > len(new_item):
            list_to_return.append(old_item)
        else:
            list_to_return.append(new_item)

    return list_to_return
