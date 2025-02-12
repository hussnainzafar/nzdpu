import datetime
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Config, Organization
from app.db.types import EN_DASH, NullTypeState
from app.routers.utils import get_choice_value, scientific_to_float
from app.service.core.cache import CoreMemoryCache
from app.service.exports.headers.headers import (
    ExportOptions,
    SearchSheets,
    get_data_explorer_headers,
    get_default_attributes_for_v40,
)
from app.service.exports.utils import (
    align_df_data_and_desc,
    clean_targets_int_data,
    format_datetime_for_downloads,
    format_value_download_all,
    get_prompt_from_key,
)
from app.service.utils import load_column_units


async def process_company_metadata(
    d: dict,
    company: Organization,
    reporting_year: int,
    session: AsyncSession,
    static_cache: CoreMemoryCache,
    exclude_classification_forced: bool | None = None,
):
    """
    Return items dict from data export list with numeration
    """
    items = {}
    # format datetime
    date_start = format_datetime_for_downloads(
        d.get("date_start_reporting_year", None)
    )
    # format datetime
    date_end = format_datetime_for_downloads(
        d.get("date_end_reporting_year", None)
    )
    # check if sics fields are available for download
    db_config_value = select(Config.value).where(
        Config.name == "data_download.exclude_classification"
    )
    # execute the query and get the result for sics available
    exclude_classification_value = await session.execute(db_config_value)
    exclude_classification = exclude_classification_value.scalars().first()
    if exclude_classification:
        exclude_classification = int(exclude_classification)
    # force to show sics values because this needs to be used in generating the excel file cache
    if exclude_classification_forced is not None:
        exclude_classification = 1 if exclude_classification_forced else 0
    sics_not_available = (
        "SICS classification information not available for download."
    )
    # create metadata for processing
    metadata_items = {
        "legal_entity_identifier": d.get("legal_entity_identifier", None),
        "legal_name": company.legal_name,
        "jurisdiction": company.jurisdiction,
        "sics_sector": (
            sics_not_available
            if exclude_classification == 1
            else company.sics_sector
        ),
        "sics_sub_sector": (
            sics_not_available
            if exclude_classification == 1
            else company.sics_sub_sector
        ),
        "sics_industry": (
            sics_not_available
            if exclude_classification == 1
            else company.sics_industry
        ),
        "data_model": d.get("data_model", None),
        "reporting_year": reporting_year,
        "date_start_reporting_year": date_start,
        "date_end_reporting_year": date_end,
        "org_boundary_approach": d.get("org_boundary_approach", None),
    }
    # create metadata description for processing
    description = {
        "legal_entity_identifier": "Legal Entity Identifier (LEI)",
        "legal_name": "Organization Legal Name",
        "jurisdiction": "Jurisdiction",
        "sics_sector": "SICS sector",
        "sics_sub_sector": "SICS sub-sector",
        "sics_industry": "SICS industry",
        "data_model": "Data model for disclosure",
        "reporting_year": "Reporting year",
        "date_start_reporting_year": "Reporting period start date",
        "date_end_reporting_year": "Reporting period end date",
        "org_boundary_approach": (
            "Organizational boundary approach used to consolidate GHG"
            " emissions"
        ),
    }
    # load choice values for metadata data
    for key, value in metadata_items.items():
        value = (
            await get_choice_value(value, session, static_cache)
            if type(value) is int and key != "reporting_year"
            else value
        )
        items[key] = value
    return items, description


async def process_scope_ghg(
    scope_ghg_list: list,
    source: str,
    last_updated: datetime.datetime,
    session: AsyncSession,
    static_cache: CoreMemoryCache,
    data_source_list=None,
):
    """
    Return items dict from scope ghg list with gas names in suffix
    """
    items = {}
    description = {}
    keys_to_remove = ["id", "obj_id", "value_id"]
    # remove keys that not need to be in processing
    new_data = [
        {k: v for k, v in item.items() if k not in keys_to_remove}
        for item in scope_ghg_list
    ]
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
    counter = 1
    for scope in new_data:
        greenhouse_has = scope.get("scope_1_greenhouse_gas")
        gas_name = await get_choice_value(
            greenhouse_has, session, static_cache
        )
        gas_name = gas_map.get(gas_name, None)
        for k, v in scope.items():
            if k.endswith("_prompt"):
                continue
            # get attribute short description
            desc = await get_prompt_from_key(
                session=session, key=k, values=scope
            )
            if k == "scope_1_greenhouse_gas":
                gas_name = await get_choice_value(v, session, static_cache)
                gas_name = gas_map.get(gas_name, None)
            if source:
                if last_updated:
                    # format last_updated value
                    v = await format_value_download_all(
                        value=v,
                        sample=last_updated,
                        value_index=1,
                        data_source_list=data_source_list,
                        session=session,
                        static_cache=static_cache,
                    )
                else:
                    # format source value
                    v = await format_value_download_all(
                        value=v,
                        sample=source,
                        value_index=0,
                        data_source_list=data_source_list,
                        session=session,
                        static_cache=static_cache,
                    )
            else:
                v = (
                    await get_choice_value(v, session, static_cache)
                    if type(v) is int
                    else v
                )
            if gas_name != "other":
                if k.startswith("scope_1_greenhouse_gas"):
                    continue
                desc = desc.format(scope_1_greenhouse_gas=gas_name.upper())
                items[f"{k}_{gas_name}"] = scientific_to_float(v)
                description[f"{k}_{gas_name}"] = desc
                if k.startswith("scope_1_ghg_emissions"):
                    k_unit = k + f"_{gas_name}_units"
                    v_unit = await load_column_units(k, session, static_cache)
                    items[f"{k_unit}"] = (
                        v_unit[0]["actions"][0]["set"]["units"]
                        if isinstance(v_unit, (dict, list))
                        else v_unit
                    )
                    description[f"{k_unit}"] = (
                        desc + " units" if desc else desc
                    )
            else:
                if k == "scope_1_greenhouse_gas":
                    continue
                k = (
                    "scope_1_greenhouse_gas"
                    if k == "scope_1_greenhouse_gas_other"
                    else k
                )
                other_gas_name = f"{gas_name}_GHG"
                desc = desc.format(scope_1_greenhouse_gas=other_gas_name)
                format_key = f"{k.replace('_ghg_', '_') if 'ghg' in k else k}_{gas_name}_{counter}"
                items[format_key] = scientific_to_float(v)
                description[format_key] = desc
                if k.startswith("scope_1_ghg_emissions"):
                    k_unit = f"{format_key}_units"
                    v_unit = await load_column_units(k, session, static_cache)
                    items[f"{k_unit}"] = (
                        v_unit[0]["actions"][0]["set"]["units"]
                        if isinstance(v_unit, (dict, list))
                        else v_unit
                    )
                    description[f"{k_unit}"] = (
                        desc + " units" if desc else desc
                    )
        if gas_name == "other":
            counter += 1
    return items, description


async def process_data_export(
    data_export_list: list | str | None,
    source: str,
    last_updated: datetime.datetime,
    form_name: str,
    session: AsyncSession,
    static_cache: CoreMemoryCache,
    download_option: str,
    restated: dict,
    data_source_list: list = None,
    rationale_assure: str = None,
    units_list: list = None,
):
    items = {}
    description = {}
    source_items = {}
    last_updated_items = {}
    units_items = {}
    keys_to_remove = ["id", "obj_id", "value_id"]
    # check if sub-form are present and assign bool for after source column
    source_check = True if data_export_list is not None else False
    # check if data is null type and assign default data
    if data_export_list in NullTypeState.values() + [None]:
        data_export_list = get_default_attributes_for_v40(
            form_name, data_export_list
        )
    # format new_data without keys_to_remove
    new_data = [
        {k: v for k, v in item.items() if k not in keys_to_remove}
        for item in data_export_list
    ]
    if rationale_assure:
        rationale_key = "rationale_emissions_assure_verif_non_disclose"
        assure_verif_headers = get_data_explorer_headers(
            SearchSheets.AV_EMISSIONS_SHEET.value
        )
        items[rationale_key] = str(rationale_assure)
        description[rationale_key] = assure_verif_headers.get(rationale_key)
    if isinstance(new_data, list):
        for counter, data in enumerate(new_data, start=1):
            for k, v in data.items():
                # format key
                key = f"{k}_{counter}"
                # skip _prompt fields
                if k.endswith("_prompt"):
                    continue
                if download_option == ExportOptions.COMPANIES.value:
                    # get attribute source from submission with null values
                    field_source = v
                    # check if source is restated and assign new source
                    if k in restated:
                        source_items[k] = restated[k][0]
                        last_updated_items[k] = format_datetime_for_downloads(
                            restated[k][1]
                        )
                    else:
                        source_items[k] = (
                            source
                            if field_source != NullTypeState.LONG_DASH
                            else EN_DASH
                        )
                        # check if field source is long dash
                        # and populate with short dash
                        last_updated_items[k] = (
                            last_updated
                            if field_source != NullTypeState.LONG_DASH.value
                            else EN_DASH
                        )
                    # get unit from sub-form
                    formatted_unit = (
                        units_list[counter - 1][k] if units_list else ""
                    )
                    units_items[key] = (
                        formatted_unit if formatted_unit != "%" else ""
                    )
                elif download_option == ExportOptions.SEARCH.value:
                    if source:
                        if last_updated:
                            # format last_updated value
                            v = await format_value_download_all(
                                value=v,
                                sample=last_updated,
                                value_index=1,
                                data_source_list=data_export_list,
                                session=session,
                                static_cache=static_cache,
                            )
                        else:
                            # format source value
                            v = await format_value_download_all(
                                value=v,
                                sample=source,
                                value_index=0,
                                data_source_list=data_source_list,
                                session=session,
                                static_cache=static_cache,
                            )
                # get attribute short description
                desc = await get_prompt_from_key(
                    session=session, key=k, values=data
                )
                # format description with counter
                desc_counter = f"{desc} ({counter})"
                # assign value to items dict
                items[key] = scientific_to_float(v)
                # assign value to description dict
                description[key] = desc_counter
    if download_option == ExportOptions.COMPANIES.value:
        return (
            items,
            description,
            source_items,
            last_updated_items,
            units_items,
        )
    return items, description


async def process_scope_emissions(
    d: dict,
    source: str,
    last_updated: datetime.datetime,
    emissions: dict,
    session: AsyncSession,
    static_cache: CoreMemoryCache,
    download_option: str,
    restated: dict,
    data_source_list: list = None,
    single: bool = None,
    units: dict = None,
):
    items = {}
    description = {}
    source_items = {}
    last_updated_items = {}
    units_items = {}
    if download_option == ExportOptions.SEARCH.value:
        keys_to_remove = ["id", "obj_id", "value_id"]
        for key in keys_to_remove:
            d.pop(key, None)
    for k, v in emissions.items():
        # check if single download is and skip None fields
        if single:
            if v is None:
                continue
        # get attribute short description
        desc = await get_prompt_from_key(session=session, key=k, values=d)
        # process attributes type multiple (just for search download still)
        if isinstance(v, list) and v is not None:
            items[k] = ""
            if source:
                if last_updated:
                    # format last_updated value
                    items[k] = await format_value_download_all(
                        value=v,
                        sample=last_updated,
                        value_index=1,
                        data_source_list=data_source_list,
                        session=session,
                        static_cache=static_cache,
                    )
                else:
                    # format source value
                    items[k] = await format_value_download_all(
                        value=v,
                        sample=source,
                        value_index=0,
                        data_source_list=data_source_list,
                        session=session,
                        static_cache=static_cache,
                    )
            else:
                for idx, value in enumerate(v):
                    value = (
                        await get_choice_value(value, session, static_cache)
                        if type(value) is int
                        else value
                    )
                    if value in NullTypeState.values():
                        items[k] = value
                    else:
                        items[k] += f"{value}"
                        if idx < len(v) - 1:
                            items[k] += ", "
            description[k] = desc
        else:
            if download_option == ExportOptions.COMPANIES.value:
                if v is not None:
                    # get attribute source from submission with null values
                    field_source = v
                    # assign value to items dict
                    items[k] = scientific_to_float(v)
                    # assign value to description dict
                    description[k] = desc
                    # check if source is restated and assign new source
                    if k in restated:
                        source_items[k] = restated[k][0]
                        last_updated_items[k] = format_datetime_for_downloads(
                            restated[k][1]
                        )
                    else:
                        source_items[k] = (
                            source
                            if field_source != NullTypeState.LONG_DASH
                            else EN_DASH
                        )
                        # check if field source is long dash
                        # and populate with short dash
                        last_updated_items[k] = (
                            last_updated
                            if field_source != NullTypeState.LONG_DASH.value
                            else EN_DASH
                        )
                    units_items[k] = (
                        units.get(k) if units.get(k) != "%" else ""
                    )
            else:
                if source:
                    if last_updated:
                        # format last_updated value
                        v = await format_value_download_all(
                            value=v,
                            sample=last_updated,
                            value_index=1,
                            data_source_list=data_source_list,
                            session=session,
                            static_cache=static_cache,
                        )
                    else:
                        # format source value
                        v = await format_value_download_all(
                            value=v,
                            sample=source,
                            value_index=0,
                            data_source_list=data_source_list,
                            session=session,
                            static_cache=static_cache,
                        )
                items[k] = scientific_to_float(v) if v is not None else EN_DASH
                description[k] = desc
                if k.startswith("total_scope"):
                    k_unit = k + "_units"
                    v_unit = await load_column_units(k, session, static_cache)
                    items[k_unit] = (
                        v_unit[0]["actions"][0]["set"]["units"]
                        if isinstance(v_unit, (dict, list))
                        else v_unit
                    )
                    description[k_unit] = desc + " units" if desc else desc

    if download_option == ExportOptions.COMPANIES.value:
        return (
            items,
            description,
            source_items,
            last_updated_items,
            units_items,
        )
    return items, description


async def process_targets_export(
    data_export_list: list | str | None,
    source: str,
    last_updated: datetime.datetime,
    units_list: list,
    form_name: str,
    session: AsyncSession,
    reporting_year: int = None,
    disclosure_year: int = None,
    target_ids: dict = None,
    progress: bool = False,
):
    items = []
    target_ids_format = {}
    keys_to_remove = [
        "id",
        "obj_id",
        "value_id",
        "tgt_abs_progress_year",
        "tgt_int_progress_year",
    ]
    # NOTE: since str and list both supports len
    source_check = len(data_export_list) > 0 if data_export_list else False
    # check if data is null type and assign default data
    if data_export_list in NullTypeState.values() + [None]:
        data_export_list = get_default_attributes_for_v40(
            form_name, data_export_list
        )
    # format new_data without keys_to_remove and units
    new_data = [
        {k: v for k, v in item.items() if k not in keys_to_remove}
        for item in data_export_list
    ]
    # target abs or int
    target_form = form_name.split("_")[1]
    # root target or target progress

    target_id_and_name = [
        f"tgt_{target_form}_id",
        f"tgt_{target_form}_name",
        f"tgt_{target_form}_id_progress",
    ]
    if isinstance(new_data, list):
        for counter, data in enumerate(new_data, start=1):
            tgt_id = data.get(
                target_id_and_name[-1] if progress else target_id_and_name[0],
                "",
            )
            tgt_name = (
                target_ids.get(tgt_id, "")
                if progress
                else data.get(target_id_and_name[1], "")
            )
            for k, v in data.items():
                # skip _prompt fields
                if (
                    k.endswith("_prompt")
                    or k in target_id_and_name
                    or "_units" in k
                ):
                    continue
                # get attribute source from submission with null values
                field_source = v
                # check if source is restated and assign new source
                source_item = (
                    source
                    if source_check
                    and field_source != NullTypeState.LONG_DASH.value
                    else EN_DASH
                )
                # get units from index and field
                formatted_unit = units_list[counter - 1].get(k)
                unit_item = formatted_unit if formatted_unit != "%" else ""
                last_updated_item = (
                    last_updated
                    if field_source != NullTypeState.LONG_DASH.value
                    else EN_DASH
                )
                # get attribute short description
                desc = await get_prompt_from_key(
                    session=session, key=k, values=data
                )

                value = (
                    scientific_to_float(v)
                    if v
                    else NullTypeState.LONG_DASH.value
                )
                data_row = {
                    "Disclosure Year": str(disclosure_year),
                    "Target ID": tgt_id,
                    "Target Name": tgt_name,
                    "Field Name": k,
                    "Short Description": desc,
                    "Units": unit_item if unit_item else "blank",
                    "Reporting Year": str(reporting_year),
                    "Value": (
                        f"{value}{'%' if formatted_unit == '%' and value != NullTypeState.LONG_DASH.value else ''}"
                    ),
                    "Source": source_item,
                    "Last Updated": last_updated_item,
                }
                if not progress:
                    target_ids_format.update({tgt_id: tgt_name})
                    data_row.pop("Reporting Year")
                items.append(data_row)
    return items, target_ids_format


async def process_assure_verif_companies(
    d: dict,
    default_headers: dict,
    reporting_year: int,
    last_updated: datetime.datetime,
    source_set: list,
    session: AsyncSession,
    restated: dict,
):
    """
    Return items dict from data with numeration
    """
    source = d.get("disclosure_source", None)
    # get rationale from root submission
    rationale_av = d.get("rationale_verif_emissions_non_disclose")
    # get assurance and verification form from submission
    assure_verif_items = d.get("verif_emissions_dict")
    items = []
    if assure_verif_items:
        # get source field form submission values with nulls
        rationale_assure = d.get("rationale_verif_emissions_non_disclose")
        # check if source is restated and assign new source
        source_map = None
        last_updated_map = None
        if isinstance(rationale_assure, list):
            if rationale_assure[0] in source_set:
                # check if source is restated and assign new source
                formatted_source = (
                    restated["rationale_verif_emissions_non_disclose"][0]
                    if "rationale_verif_emissions_non_disclose" in restated
                    else source
                )
                source_map = (
                    formatted_source
                    if rationale_assure != NullTypeState.LONG_DASH.value
                    else EN_DASH
                )
        last_updated_map = (
            last_updated
            if rationale_assure != NullTypeState.LONG_DASH.value
            else EN_DASH
        )
        # format rationale root attribute for export
        rationale_row = {
            "Field Name": "rationale_verif_emissions_non_disclose",
            "Short Description": (
                "Rationale if verification of GHG emissions not disclosed"
            ),
            "Reporting Year": reporting_year,
            "Value": scientific_to_float(rationale_av),
            "Source": (
                source_map
                if rationale_av != NullTypeState.LONG_DASH.value
                else EN_DASH
            ),
            "Last Updated": (
                last_updated_map if last_updated_map else last_updated
            ),
            "Restated": (
                "Yes"
                if source_map != source
                and source_map not in [NullTypeState.DASH.value, None]
                else None
            ),
        }
        items.append(rationale_row)
        for counter, row in enumerate(assure_verif_items, start=1):
            if isinstance(row, dict):
                for key, value in row.items():
                    # skip _prompt fields and key to remove
                    if key.endswith("_prompt"):
                        continue
                    # get source field form submission values with nulls
                    field_source = value
                    # get attribute short description
                    desc = await get_prompt_from_key(
                        session=session, key=key, values=row
                    )
                    if key not in ["id", "obj_id", "value_id"]:
                        # check if source is restated and assign new source
                        formatted_source = (
                            restated[key] if key in restated else source
                        )
                        source_map = (
                            formatted_source
                            if field_source != NullTypeState.LONG_DASH.value
                            else EN_DASH
                        )
                        last_updated_map = (
                            last_updated
                            if field_source != NullTypeState.LONG_DASH.value
                            else EN_DASH
                        )
                        key_other = None
                        # format _other attributes with counter before other
                        if key.endswith("_other"):
                            formatter = key.split("_other")
                            key_other = f"{formatter[0]}_{counter}_other"
                        data_row = {
                            "Field Name": (
                                key_other if key_other else f"{key}_{counter}"
                            ),
                            "Short Description": f"{desc} ({counter})",
                            "Reporting Year": reporting_year,
                            "Value": scientific_to_float(value),
                            "Source": source_map,
                            "Last Updated": last_updated_map,
                            "Restated": (
                                "Yes"
                                if source_map != source
                                and source_map
                                not in [
                                    NullTypeState.DASH.value,
                                    EN_DASH,
                                    None,
                                ]
                                else EN_DASH
                            ),
                        }
                        items.append(data_row)
    else:
        # iterate adding default headers
        for k, v in default_headers.items():
            rationale_data = d.get(
                "rationale_verif_emissions_non_disclose", None
            )
            # first process root attribute for assurance and verification
            if k == "rationale_verif_emissions_non_disclose":
                assure_row = {
                    "Field Name": k,
                    "Short Description": v,
                    "Reporting Year": reporting_year,
                    "Value": (
                        scientific_to_float(rationale_data)
                        if rationale_data
                        else NullTypeState.LONG_DASH.value
                    ),
                    "Source": (
                        source if rationale_data is not None else EN_DASH
                    ),
                    "Last Updated": (
                        last_updated if rationale_data is not None else EN_DASH
                    ),
                    "Restated": None,
                }
                items.append(assure_row)
            else:
                if k == "rationale_verif_emissions_non_disclose":
                    assure_value = (
                        rationale_data if rationale_data else EN_DASH
                    )
                    assure_source = (
                        source if rationale_data is not None else EN_DASH
                    )
                else:
                    assure_value = NullTypeState.LONG_DASH.value
                    assure_source = (
                        source if assure_verif_items is not None else EN_DASH
                    )
                    assure_last_updated = (
                        (
                            last_updated
                            if rationale_data is not None
                            else EN_DASH
                        ),
                    )
                assure_row = {
                    "Field Name": k,
                    "Short Description": v,
                    "Reporting Year": reporting_year,
                    "Value": scientific_to_float(assure_value),
                    "Source": assure_source,
                    "Last Updated": assure_last_updated,
                    "Restated": None,
                }
                items.append(assure_row)
    return items


async def process_target_validation_companies(
    d: dict,
    disclosure_year: int,
    last_updated: datetime.datetime,
    form_name: str,
    session: AsyncSession,
    target_ids: dict,
):
    """
    Return items dict from data with numeration
    """
    source = d.get("disclosure_source", None)
    target_form = form_name.split("_")[1]
    # get assurance and verification form from submission
    target_validation = d.get(form_name)
    items = []
    if isinstance(target_validation, list) and target_validation[-1].get(
        f"tgt_{target_form}_id_valid"
    ) not in (NullTypeState.LONG_DASH.value, None):
        for counter, row in enumerate(target_validation, start=1):
            tgt_id = row.get(f"tgt_{target_form}_id_valid")
            tgt_name = target_ids.get(tgt_id)
            if isinstance(row, dict):
                for key, value in row.items():
                    # skip _prompt fields and key to remove
                    if key.endswith("_prompt"):
                        continue
                    # get source field form submission values with nulls
                    field_source = value
                    # get attribute short description
                    desc = await get_prompt_from_key(
                        session=session, key=key, values=row
                    )
                    if key not in [
                        "id",
                        "obj_id",
                        "value_id",
                        f"tgt_{target_form}_id_valid",
                    ]:
                        # check if source is restated and assign new source
                        source_map = (
                            source
                            if field_source != NullTypeState.LONG_DASH.value
                            else EN_DASH
                        )
                        last_updated_map = (
                            last_updated
                            if field_source != NullTypeState.LONG_DASH.value
                            else EN_DASH
                        )
                        key_other = None
                        # format _other attributes with counter begore other
                        if key.endswith("_other"):
                            formatter = key.split("_other")
                            key_other = f"{formatter[0]}_{counter}_other"
                        data_row = {
                            "Disclosure Year": disclosure_year,
                            "Target ID": tgt_id,
                            "Target Name": tgt_name,
                            "Field Name": (
                                key_other if key_other else f"{key}_{counter}"
                            ),
                            "Short Description": f"{desc} ({counter})",
                            "Value": (
                                scientific_to_float(value)
                                if value
                                else NullTypeState.LONG_DASH.value
                            ),
                            "Source": source_map,
                            "Last Updated": last_updated_map,
                        }
                        items.append(data_row)
    return items


async def process_targets_and_progress(
    targets: dict[str, Any],
    target: str,
    session: AsyncSession,
    static_cache: CoreMemoryCache,
    source=None,
    last_updated=None,
    data_source_list=None,
):
    """
    Return dict from targets list
    """
    targets_items = {}
    targets_desc = {}
    targets_progress = {}
    targets_progress_desc = {}
    keys_to_remove = [
        "id",
        "obj_id",
        "value_id",
        "abs_target_coverage_sector_list",
        "abs_progress_absolute_target",
        "int_ph_target_coverage_sector_list",
        "int_ph_progress_intensity_target",
    ]
    target_id = targets.get(f"tgt_{target}id")
    target_name = targets.get(f"tgt_{target}name")
    if target == "abs_":
        targets_progress_data = targets.get("abs_progress_absolute_target")
        if isinstance(targets_progress_data, list):
            if targets_progress_data:
                (
                    target_progress,
                    target_progress_desc,
                ) = await process_nested_targets_progress(
                    targets_progress_data,
                    target_id,
                    target_name,
                    target,
                    session,
                    source,
                    last_updated,
                )
                targets_progress.update(target_progress)
                targets_progress_desc.update(target_progress_desc)
    elif target == "int_":
        await process_target_int_data(
            targets.get("target_int_physical"),
            "int_ph_progress_intensity_target",
            target_id,
            target_name,
            target,
            session,
            static_cache,
            source,
            last_updated,
            targets_progress,
            targets_progress_desc,
        )

        await process_target_int_data(
            targets.get("target_int_economic"),
            "int_ec_progress_intensity_economic_target",
            target_id,
            target_name,
            target,
            session,
            static_cache,
            source,
            last_updated,
            targets_progress,
            targets_progress_desc,
        )
    for keys in keys_to_remove:
        targets.pop(keys, None)
    if target == "abs_":
        if isinstance(targets, dict):
            for k, v in targets.items():
                if k.endswith("_prompt"):
                    continue
                desc = await get_prompt_from_key(
                    session=session, key=k, values=targets
                )
                k_with_counter = k
                if isinstance(v, list):
                    targets_items[k_with_counter] = ""
                    if source:
                        if last_updated:
                            # format last_updated value
                            i = await format_value_download_all(
                                value=v,
                                sample=last_updated,
                                value_index=1,
                                data_source_list=data_source_list,
                                session=session,
                                static_cache=static_cache,
                            )
                        else:
                            # format source value
                            i = await format_value_download_all(
                                value=v,
                                sample=source,
                                value_index=0,
                                data_source_list=data_source_list,
                                session=session,
                                static_cache=static_cache,
                            )
                        targets_items[k_with_counter] = i
                    else:
                        for idx, i in enumerate(v):
                            i = (
                                await get_choice_value(
                                    i, session, static_cache
                                )
                                if type(i) is int
                                else i
                            )
                            if i in NullTypeState.values():
                                targets_items[k_with_counter] = i
                            else:
                                targets_items[k_with_counter] += f"{i}"
                                if idx < len(v) - 1:
                                    targets_items[k_with_counter] += ", "
                    targets_desc[k_with_counter] = desc
                else:
                    if source and k not in ["tgt_abs_id", "tgt_abs_name"]:
                        if last_updated:
                            # format last_updated value
                            v = await format_value_download_all(
                                value=v,
                                sample=last_updated,
                                value_index=1,
                                data_source_list=data_source_list,
                                session=session,
                                static_cache=static_cache,
                            )
                        else:
                            # format source value
                            v = await format_value_download_all(
                                value=v,
                                sample=source,
                                value_index=0,
                                data_source_list=data_source_list,
                                session=session,
                                static_cache=static_cache,
                            )
                    else:
                        v = (
                            await get_choice_value(v, session, static_cache)
                            if type(v) is int
                            else v
                        )
                    targets_items[k_with_counter] = scientific_to_float(v)
                    targets_desc[k_with_counter] = desc
    elif target == "int_":
        clean_targets_int_data("target_int_physical", targets, keys_to_remove)
        clean_targets_int_data("target_int_economic", targets, keys_to_remove)
        target_int_physical = {}
        target_int_physical_desc = {}
        target_int_economic = {}
        target_int_economic_desc = {}
        target_progress_skip = [
            "int_ph_progress_intensity_target",
            "int_ec_progress_intensity_economic_target",
        ]

        if isinstance(targets, dict):
            for k, v in targets.items():
                if isinstance(v, list):
                    co_int_phys_sec = 0
                    co_int_econ_sec = 0
                    for i in v:
                        if isinstance(i, dict):
                            for key, value in i.items():
                                if key.endswith("_prompt"):
                                    continue
                                desc = await get_prompt_from_key(
                                    session=session, key=key, values=i
                                )
                                if isinstance(value, list):
                                    co_int_phys_thr = 0
                                    co_int_econ_thr = 0
                                    if key not in target_progress_skip:
                                        n_value = ""
                                        if source:
                                            if last_updated:
                                                # format last_updated value
                                                n_value = await format_value_download_all(
                                                    value=value,
                                                    sample=last_updated,
                                                    value_index=1,
                                                    data_source_list=data_source_list,
                                                    session=session,
                                                    static_cache=static_cache,
                                                )
                                            else:
                                                # format source value
                                                n_value = await format_value_download_all(
                                                    value=value,
                                                    sample=source,
                                                    value_index=0,
                                                    data_source_list=data_source_list,
                                                    session=session,
                                                    static_cache=static_cache,
                                                )
                                        else:
                                            for idx, n in enumerate(value):
                                                n = (
                                                    await get_choice_value(
                                                        n,
                                                        session,
                                                        static_cache,
                                                    )
                                                    if type(n) is int
                                                    else n
                                                )
                                                n_value += f"{n_value}"
                                                if idx < len(value) - 1:
                                                    n_value += ", "
                                        if key.startswith("tgt_phys"):
                                            if (
                                                co_int_phys_sec == 0
                                                and co_int_phys_thr == 0
                                            ):
                                                key_thr = key
                                            else:
                                                key_thr = f"{key}_{co_int_phys_sec}_{co_int_phys_thr}"
                                            target_int_physical[key_thr] = (
                                                scientific_to_float(n_value)
                                            )
                                            target_int_physical_desc[
                                                key_thr
                                            ] = desc
                                            co_int_phys_thr += 1
                                        elif key.startswith("tgt_econ"):
                                            if (
                                                co_int_econ_sec == 0
                                                and co_int_econ_thr == 0
                                            ):
                                                key_thr = key
                                            else:
                                                key_thr = f"{key}_{co_int_econ_sec}_{co_int_econ_thr}"
                                            target_int_economic[key_thr] = (
                                                scientific_to_float(n_value)
                                            )
                                            target_int_economic_desc[
                                                key_thr
                                            ] = desc
                                            co_int_econ_thr += 1
                                else:
                                    if source:
                                        if last_updated:
                                            # format last_updated value
                                            value = await format_value_download_all(
                                                value=value,
                                                sample=last_updated,
                                                value_index=1,
                                                data_source_list=data_source_list,
                                                session=session,
                                                static_cache=static_cache,
                                            )
                                        else:
                                            # format source value
                                            value = await format_value_download_all(
                                                value=value,
                                                sample=source,
                                                value_index=0,
                                                data_source_list=data_source_list,
                                                session=session,
                                                static_cache=static_cache,
                                            )
                                    else:
                                        value = (
                                            await get_choice_value(
                                                value, session, static_cache
                                            )
                                            if type(value) is int
                                            else value
                                        )
                                    if key.startswith("tgt_phys"):
                                        key_sec = (
                                            f"{key}_{co_int_phys_sec}"
                                            if co_int_phys_sec != 0
                                            else key
                                        )
                                        target_int_physical[key_sec] = (
                                            scientific_to_float(value)
                                        )
                                        target_int_physical_desc[key_sec] = (
                                            desc
                                        )
                                        co_int_phys_sec += 1
                                    elif key.startswith("tgt_econ"):
                                        key_sec = (
                                            f"{key}_{co_int_econ_sec}"
                                            if co_int_econ_sec != 0
                                            else key
                                        )
                                        target_int_economic[key_sec] = (
                                            scientific_to_float(value)
                                        )
                                        target_int_economic_desc[key_sec] = (
                                            desc
                                        )
                                        co_int_econ_sec += 1
                else:
                    if k.endswith("_prompt"):
                        continue
                    desc = await get_prompt_from_key(
                        session=session, key=k, values=targets
                    )
                    if source and k not in ["tgt_int_id", "tgt_int_name"]:
                        if last_updated:
                            # format last_updated value
                            v = await format_value_download_all(
                                value=v,
                                sample=last_updated,
                                value_index=1,
                                data_source_list=data_source_list,
                                session=session,
                                static_cache=static_cache,
                            )
                        else:
                            # format source value
                            v = await format_value_download_all(
                                value=v,
                                sample=source,
                                value_index=0,
                                data_source_list=data_source_list,
                                session=session,
                                static_cache=static_cache,
                            )
                    else:
                        v = (
                            await get_choice_value(v, session, static_cache)
                            if type(v) is int
                            else v
                        )
                    target_int_physical[k] = str(v)
                    target_int_physical_desc[k] = desc
                    target_int_economic[k] = str(v)
                    target_int_economic_desc[k] = desc
        targets_items = {
            "target_int_physical": target_int_physical,
            "target_int_economic": target_int_economic,
        }
        targets_desc = {
            "target_int_physical": target_int_physical_desc,
            "target_int_economic": target_int_economic_desc,
        }
    return targets_items, targets_progress, targets_desc, targets_progress_desc


async def process_dataframe_data(
    data, desc, df_full, unchanged_data=None, unchanged_desc_data=None
):
    """
    Process dataframes from response
    """
    data_ucd = (
        {**unchanged_data, **data}
        if unchanged_data and unchanged_desc_data
        else data
    )
    desc_data = (
        {**unchanged_desc_data, **desc}
        if unchanged_data and unchanged_desc_data
        else desc
    )

    new_headers = [
        key for key in desc_data.keys() if key not in df_full.columns
    ]
    if new_headers:
        new_headers_df = pd.DataFrame(index=[0, 1], columns=list(new_headers))
        new_headers_df.iloc[0] = [key.upper() for key in new_headers]
        new_headers_df.iloc[1] = [desc_data[key] for key in new_headers]
        df_full = pd.concat([df_full, new_headers_df], axis=1)
    desc_data_aligned = align_df_data_and_desc(data_ucd, desc_data)
    data_df = pd.DataFrame(
        [list(data_ucd.values())], columns=list(desc_data_aligned.keys())
    )
    df_full = pd.concat([df_full, data_df], ignore_index=True)

    return df_full


async def process_target_int_data(
    target_data,
    target_type,
    target_id,
    target_name,
    target,
    session,
    static_cache: CoreMemoryCache,
    source,
    last_updated,
    targets_progress,
    targets_progress_desc,
):
    """
    Process intensity sub-forms (physical and economic)
    """
    if isinstance(target_data, list):
        for target_pro in target_data:
            targets_progress_data = target_pro.get(target_type)
            (
                target_progress,
                target_progress_desc,
            ) = await process_nested_targets_progress(
                targets_progress_data,
                target_id,
                target_name,
                target,
                session,
                static_cache,
                source,
                last_updated,
            )
            targets_progress.update({target_type: target_progress})
            targets_progress_desc.update({target_type: target_progress_desc})


async def process_nested_targets_progress(
    targets_list,
    targets_id,
    targets_name,
    spliter,
    session,
    static_cache,
    source=None,
    last_updated=None,
    data_source_list=None,
):
    """
    Return processed dict from nested targets
    """
    items = {}
    description = {}
    if not isinstance(targets_list, list):
        return items, description
    if isinstance(targets_list, list):
        for counter_sec, data in enumerate(targets_list, start=0):
            new_data = {
                **{f"tgt_{spliter}id": targets_id},
                **{f"tgt_{spliter}name": targets_name},
                **data,
            }
            for k, v in new_data.items():
                if spliter in k:
                    if k.endswith("_prompt"):
                        continue
                    # get attribute prompt
                    desc = await get_prompt_from_key(
                        session=session, key=k, values=new_data
                    )
                    if source and k not in [
                        f"tgt_{spliter}id",
                        f"tgt_{spliter}name",
                    ]:
                        if last_updated:
                            # format last_updated value
                            v = await format_value_download_all(
                                value=v,
                                sample=last_updated,
                                value_index=1,
                                data_source_list=data_source_list,
                                session=session,
                                static_cache=static_cache,
                            )
                        else:
                            # format source value
                            v = await format_value_download_all(
                                value=v,
                                sample=source,
                                value_index=0,
                                data_source_list=data_source_list,
                                session=session,
                                static_cache=static_cache,
                            )
                    else:
                        v = (
                            await get_choice_value(v, session, static_cache)
                            if type(v) is int
                            else v
                        )
                    if counter_sec == 0:
                        key = f"{k}"
                    else:
                        key = f"{k}_{counter_sec}"
                    items[key] = scientific_to_float(v)
                    description[key] = desc
    return items, description


async def process_financed_emissions(
    d: dict[str, Any],
    session: AsyncSession,
    static_cache: CoreMemoryCache,
    source=None,
    last_updated=None,
    parent_key="",
    counter_dict=None,
    data_source_list=None,
):
    items = {}
    description = {}
    keys_to_remove = ["id", "obj_id", "value_id"]
    for key in keys_to_remove:
        d.pop(key, None)
    if counter_dict is None:
        counter_dict = {}

    for k, v in d.items():
        if k.endswith("_prompt"):
            continue
        new_key = f"{parent_key}_{k}" if parent_key else k

        # count similar keys to add a suffix for list elements
        if new_key not in counter_dict:
            counter_dict[new_key] = 1
        else:
            counter_dict[new_key] += 1

        # get attribute short description
        desc = await get_prompt_from_key(session=session, key=k, values=d)

        if isinstance(v, dict):
            (
                processed_items,
                processed_description,
            ) = await process_financed_emissions(
                v, session, source, last_updated, new_key, counter_dict
            )
            items.update(processed_items)
            description.update(processed_description)
        elif isinstance(v, list):
            for i, elem in enumerate(v, 1):
                if isinstance(elem, (dict, list)):
                    (
                        processed_items,
                        processed_description,
                    ) = await process_financed_emissions(
                        elem,
                        session,
                        source,
                        last_updated,
                        f"{new_key}_{i}",
                        counter_dict,
                    )
                    items.update(processed_items)
                    description.update(processed_description)
                else:
                    if source:
                        if last_updated:
                            # format last_updated value
                            elem = await format_value_download_all(
                                value=elem,
                                sample=last_updated,
                                value_index=1,
                                data_source_list=data_source_list,
                                session=session,
                                static_cache=static_cache,
                            )
                        else:
                            # format source value
                            elem = await format_value_download_all(
                                value=elem,
                                sample=source,
                                value_index=0,
                                data_source_list=data_source_list,
                                session=session,
                                static_cache=static_cache,
                            )
                    else:
                        elem = (
                            await get_choice_value(elem, session, static_cache)
                            if isinstance(elem, int)
                            else elem
                        )
                    items[f"{new_key}_{counter_dict[new_key]}"] = (
                        scientific_to_float(elem)
                    )
                    description[f"{new_key}_{counter_dict[new_key]}"] = desc
                    if new_key.endswith("usd"):
                        k_unit = new_key + "_units"
                        v_unit = await load_column_units(
                            k, session, static_cache
                        )
                        items[f"{k_unit}_{counter_dict[new_key]}"] = (
                            v_unit[0]["actions"][0]["set"]["units"]
                            if isinstance(v_unit, (dict, list))
                            else v_unit
                        )
                        description[f"{k_unit}_{counter_dict[new_key]}"] = (
                            desc + " units" if desc else desc
                        )
        else:
            if source:
                if last_updated:
                    # format last_updated value
                    v = await format_value_download_all(
                        value=v,
                        sample=last_updated,
                        value_index=1,
                        data_source_list=data_source_list,
                        session=session,
                        static_cache=static_cache,
                    )
                else:
                    # format source value
                    v = await format_value_download_all(
                        value=v,
                        sample=source,
                        value_index=0,
                        data_source_list=data_source_list,
                        session=session,
                        static_cache=static_cache,
                    )
            else:
                v = (
                    await get_choice_value(v, session, static_cache)
                    if isinstance(v, int)
                    else v
                )
            items[new_key] = scientific_to_float(v)
            description[new_key] = desc
            if new_key.endswith("usd") and not new_key.startswith("fn"):
                k_unit = new_key + "_units"
                v_unit = await load_column_units(k, session, static_cache)
                items[k_unit] = (
                    v_unit[0]["actions"][0]["set"]["units"]
                    if isinstance(v_unit, (dict, list))
                    else v_unit
                )
                description[k_unit] = desc + " units" if desc else desc

    return items, description


async def process_target_validations(
    target_validation: dict,
    rationale_target: str | None,
    session: AsyncSession,
    static_cache: CoreMemoryCache,
    source=None,
    last_updated=None,
    data_source_list=None,
):
    """
    Return items dict from target validation with numeration
    """
    counter_list = []
    items = {}
    description = {}
    keys_to_remove = ["id", "obj_id", "value_id"]
    new_data = [
        {k: v for k, v in target_validation.items() if k not in keys_to_remove}
    ]
    if isinstance(new_data, list):
        for counter, data in enumerate(new_data, start=0):
            counter_list.append(counter)
            for k, v in data.items():
                if k.endswith("_prompt"):
                    continue
                key_counter = f"{k}_{counter}" if counter != 0 else k
                if k.startswith("target_id"):
                    k_abs_change = key_counter.replace("target", "tgt_abs")
                    k_int_change = key_counter.replace("target", "tgt_int")
                    items[k_abs_change] = str(v) if "ABS" in v else ""
                    description[k_abs_change] = "Target ID"
                    items[k_int_change] = str(v) if "INT" in v else ""
                    description[k_int_change] = "Target ID"

                else:
                    # get attribute short description
                    desc = await get_prompt_from_key(
                        session=session, key=k, values=data
                    )
                    key_counter = f"{k}_{counter}" if counter != 0 else k
                    if source:
                        if last_updated:
                            # format last_updated value
                            v = await format_value_download_all(
                                value=v,
                                sample=last_updated,
                                value_index=1,
                                data_source_list=data_source_list,
                                session=session,
                                static_cache=static_cache,
                            )
                        else:
                            # format source value
                            v = await format_value_download_all(
                                value=v,
                                sample=source,
                                value_index=0,
                                data_source_list=data_source_list,
                                session=session,
                                static_cache=static_cache,
                            )
                    else:
                        v = (
                            await get_choice_value(v, session, static_cache)
                            if type(v) is int
                            else v
                        )

                    items[key_counter] = scientific_to_float(v)
                    description[key_counter] = desc
            key = (
                f"rationale_target_valid_non_disclose_{counter}"
                if counter != 0
                else "rationale_target_valid_non_disclose"
            )
            items = {
                **items,
                **{key: rationale_target},
            }
            description = {
                **description,
                **{
                    key: (
                        "Rationale if validation of GHG emissions reduction"
                        " targets is not disclosed"
                    )
                },
            }

    return items, description


async def process_scope_3_nested_lists(
    scope_list,
    scope_group,
    counter,
    session,
    static_cache: CoreMemoryCache,
    category_desc=None,
    source=None,
    last_updated=None,
    data_source_list=None,
):
    """
    Return nested items dict from scope 3 ghg protocol
    """
    items = {}
    description = {}
    for i in range(1, 17):
        (
            items.update({f"scope_3_c{counter}_data": {}})
            if i != 16
            else items.update({"scope_3_other_data": {}})
        )
        (
            description.update({f"scope_3_c{counter}_desc": {}})
            if i != 16
            else description.update({"scope_3_other_desc": {}})
        )
    if not isinstance(scope_list, list):
        return items, description
    keys_to_remove = ["id", "obj_id", "value_id"]
    new_data = [
        {k: v for k, v in item.items() if k not in keys_to_remove}
        for item in scope_list
    ]
    if isinstance(new_data, list):
        for counter_sec, data in enumerate(new_data, start=1):
            for k, v in data.items():
                if k.endswith("_prompt"):
                    continue
                # get attribute short description
                desc = await get_prompt_from_key(
                    session=session, key=k, values=data
                )
                desc = (
                    desc.format(scope_3_ghgp_category=category_desc)
                    if scope_group == "ghgp"
                    else desc.format(scope_3_iso_category=category_desc)
                )
                if source:
                    if last_updated:
                        # format last_updated value
                        v = await format_value_download_all(
                            value=v,
                            sample=last_updated,
                            value_index=1,
                            data_source_list=data_source_list,
                            session=session,
                            static_cache=static_cache,
                        )
                    else:
                        # format source value
                        v = await format_value_download_all(
                            value=v,
                            sample=source,
                            value_index=0,
                            data_source_list=data_source_list,
                            session=session,
                            static_cache=static_cache,
                        )
                else:
                    v = (
                        await get_choice_value(v, session, static_cache)
                        if type(v) is int
                        else v
                    )
                format_key = k.replace(
                    f"{scope_group}",
                    (
                        f"{scope_group}_c{counter}"
                        if counter != 16
                        else f"{scope_group}_other"
                    ),
                )
                key = f"{format_key}_{counter_sec}"
                items[
                    (
                        f"scope_3_c{counter}_data"
                        if counter != 16
                        else "scope_3_other_data"
                    )
                ].update({key: scientific_to_float(v)})
                description[
                    (
                        f"scope_3_c{counter}_desc"
                        if counter != 16
                        else "scope_3_other_desc"
                    )
                ].update({key: desc})

    return items, description


async def process_scope_3(
    scope_list: list,
    scope_source: dict,
    scope_group: str,
    session: AsyncSession,
    static_cache: CoreMemoryCache,
    form_name: str,
    source=None,
    last_updated=None,
    single=False,
    data_source_list=None,
):
    """
    Return items dict from data export list with numeration
    """
    scope_emissions_items = {}
    scope_description = {}
    methodology_items = {}
    methodology_description = {}
    exclusion_items = {}
    exclusion_description = {}
    keys_to_remove = [
        "id",
        "obj_id",
        "value_id",
        f"scope_3_{scope_group}_emissions",
        f"scope_3_{scope_group}_emissions_units",
        f"disclose_s3_{scope_group}_cat_yn",
        f"disclose_s3_{scope_group}_methodology_yn",
        f"scope_3_{scope_group}_methodology",
        f"scope_3_{scope_group}_exclusion",
        f"disclose_s3_{scope_group}_exclusion_yn",
    ]
    optional_other = [
        f"scope_3_{scope_group}_category",
        f"scope_3_{scope_group}_relevancy",
        f"scope_3_{scope_group}_relevancy_description",
        f"rationale_s3_{scope_group}_non_disclose",
    ]
    disclose_to_remove = []
    if single:
        disclose_to_remove = [
            f"disclose_s3_{scope_group}_methodology_yn",
            f"disclose_s3_{scope_group}_exclusion_yn",
        ]
        for disclose in disclose_to_remove:
            keys_to_remove.remove(disclose)
    for counter, data in enumerate(scope_list, start=1):
        category_desc_value = next(
            (va for ke, va in data.items() if ke.endswith("category")),
            None,
        )
        category_counter = counter
        if (
            category_desc_value is not None
            and category_desc_value not in NullTypeState.values()
        ):
            category_counter = category_desc_value % 100

        category_desc = await get_choice_value(
            category_desc_value, session, static_cache
        )
        # format description for -other = 100016 different from standard
        category_desc = category_desc if category_counter != 16 else "Other"
        methodology_data = data.get(f"scope_3_{scope_group}_methodology", None)
        exclusion_data = data.get(f"scope_3_{scope_group}_exclusion", None)
        if methodology_data:
            (
                methodology,
                methodology_desc,
            ) = await process_scope_3_nested_lists(
                methodology_data,
                scope_group,
                category_counter,
                session,
                static_cache,
                category_desc,
                source,
                last_updated,
            )
            if methodology and methodology_desc:
                methodology_items.update(methodology)
                methodology_description.update(methodology_desc)
            else:
                scope_3_methodology_headers = get_data_explorer_headers(
                    SearchSheets.SCOPE_3_METHODOLOGY_SHEET.value
                )
                scope_m_type = (
                    f"scope_3_{scope_group}_c{counter}_methodology_type_1"
                )
                scope_m_type_other = f"scope_3_{scope_group}_c{counter}_methodology_type_other_1"
                scope_m_desc_methodology = f"scope_3_{scope_group}_c{counter}_methodology_description_1"
                scope_m_perc = (
                    f"scope_3_{scope_group}_c{counter}_methodology_perc_1"
                )
                default_m = {
                    (
                        f"scope_3_c{category_counter}_data"
                        if category_counter != 16
                        else "scope_3_other_data"
                    ): {}
                }
                default_m_desc = {
                    (
                        f"scope_3_c{category_counter}_desc"
                        if category_counter != 16
                        else "scope_3_other_desc"
                    ): {}
                }
                default_methodology = {
                    scope_m_type: None,
                    scope_m_type_other: None,
                    scope_m_desc_methodology: None,
                    scope_m_perc: None,
                }
                default_methodology_desc = {
                    scope_m_type: scope_3_methodology_headers.get(
                        scope_m_type
                    ),
                    scope_m_type_other: scope_3_methodology_headers.get(
                        scope_m_type_other
                    ),
                    scope_m_desc_methodology: scope_3_methodology_headers.get(
                        scope_m_desc_methodology
                    ),
                    scope_m_perc: scope_3_methodology_headers.get(
                        scope_m_perc
                    ),
                }
                default_m[
                    (
                        f"scope_3_c{category_counter}_data"
                        if category_counter != 16
                        else "scope_3_other_data"
                    )
                ].update(default_methodology)
                default_m_desc[
                    (
                        f"scope_3_c{category_counter}_desc"
                        if category_counter != 16
                        else "scope_3_other_desc"
                    )
                ].update(default_methodology_desc)
                methodology_items.update(default_methodology)
                methodology_description.update(default_methodology_desc)
        if exclusion_data:
            exclusion, exclusion_desc = await process_scope_3_nested_lists(
                exclusion_data,
                scope_group,
                category_counter,
                session,
                static_cache,
                category_desc,
                source,
                last_updated,
            )
            if exclusion and exclusion_desc:
                exclusion_items.update(exclusion)
                exclusion_description.update(exclusion_desc)
            else:
                scope_3_exclusion_headers = get_data_explorer_headers(
                    SearchSheets.SCOPE_3_EXCLUSIONS_SHEET.value
                )
                scope_e_desc = (
                    f"scope_3_{scope_group}_c{counter}_exclusion_description_1"
                )
                scope_e_exp = (
                    f"scope_3_{scope_group}_c{counter}_exclusion_explanation_1"
                )
                scope_e_perc = (
                    f"scope_3_{scope_group}_c{counter}_exclusion_perc_1"
                )
                scope_e_perc_exp = f"scope_3_{scope_group}_c{counter}_exclusion_perc_explanation_1"
                default_e = {
                    (
                        f"scope_3_c{category_counter}_data"
                        if category_counter != 16
                        else "scope_3_other_data"
                    ): {}
                }
                default_e_desc = {
                    (
                        f"scope_3_c{category_counter}_desc"
                        if category_counter != 16
                        else "scope_3_other_desc"
                    ): {}
                }
                default_exclusion = {
                    scope_e_desc: None,
                    scope_e_exp: None,
                    scope_e_perc: None,
                    scope_e_perc_exp: None,
                }
                default_exclusion_desc = {
                    scope_e_desc: scope_3_exclusion_headers.get(scope_e_desc),
                    scope_e_exp: scope_3_exclusion_headers.get(scope_e_exp),
                    scope_e_perc: scope_3_exclusion_headers.get(scope_e_perc),
                    scope_e_perc_exp: scope_3_exclusion_headers.get(
                        scope_e_perc_exp
                    ),
                }
                default_e[
                    (
                        f"scope_3_c{category_counter}_data"
                        if category_counter != 16
                        else "scope_3_other_data"
                    )
                ].update(default_exclusion)
                default_e_desc[
                    (
                        f"scope_3_c{category_counter}_desc"
                        if category_counter != 16
                        else "scope_3_other_desc"
                    )
                ].update(default_exclusion_desc)
                exclusion_items.update(default_exclusion)
                exclusion_description.update(default_exclusion_desc)
        new_data = {**scope_source, **data}
        for k, v in new_data.items():
            if k.endswith("_prompt") or k in keys_to_remove:
                continue
            # get attribute prompt
            desc = await get_prompt_from_key(
                session=session, key=k, values=new_data
            )
            desc = (
                desc.format(scope_3_ghgp_category=category_desc)
                if scope_group == "ghgp"
                else desc.format(scope_3_iso_category=category_desc)
            )
            if isinstance(v, list):
                k = k.replace(
                    f"{scope_group}",
                    (
                        f"{scope_group}_c{category_counter}"
                        if category_counter != 16
                        else f"{scope_group}_other"
                    ),
                )
                scope_emissions_items[k] = ""
                if source:
                    if last_updated:
                        # format last_updated value
                        v = await format_value_download_all(
                            value=v,
                            sample=last_updated,
                            value_index=1,
                            data_source_list=data_source_list,
                            session=session,
                            static_cache=static_cache,
                        )
                    else:
                        # format source value
                        v = await format_value_download_all(
                            value=v,
                            sample=source,
                            value_index=0,
                            data_source_list=data_source_list,
                            session=session,
                            static_cache=static_cache,
                        )
                    scope_emissions_items[k] = scientific_to_float(v)
                else:
                    for idx, i in enumerate(v):
                        i = (
                            await get_choice_value(i, session, static_cache)
                            if type(i) is int
                            else i
                        )
                        if i in NullTypeState.values():
                            scope_emissions_items[k] = i
                        else:
                            scope_emissions_items[k] += f"{i}"
                            if idx < len(v) - 1:
                                scope_emissions_items[k] += ", "
                scope_description[k] = desc
            else:
                if source:
                    if last_updated:
                        # format last_updated value
                        v = await format_value_download_all(
                            value=v,
                            sample=last_updated,
                            value_index=1,
                            data_source_list=data_source_list,
                            session=session,
                            static_cache=static_cache,
                        )
                    else:
                        # format source value
                        v = await format_value_download_all(
                            value=v,
                            sample=source,
                            value_index=0,
                            data_source_list=data_source_list,
                            session=session,
                            static_cache=static_cache,
                        )
                else:
                    v = (
                        await get_choice_value(v, session, static_cache)
                        if type(v) is int
                        else v
                    )
                if k in disclose_to_remove:
                    # check if field are in disclose and assing them Yes/No
                    v = "Yes" if v else "No" if v is not None else "-"
                if category_counter != 16:
                    if k == f"scope_3_{scope_group}_category_other":
                        continue
                    format_key = k.replace(
                        f"{scope_group}",
                        f"{scope_group}_c{category_counter}",
                    )
                    key = format_key
                    scope_emissions_items[key] = scientific_to_float(v)
                    scope_description[key] = desc
                    if k.endswith("ghg") or k.endswith("co2"):
                        k_unit = key + "_units"
                        v_unit = await load_column_units(
                            k, session, static_cache
                        )
                        scope_emissions_items[k_unit] = (
                            v_unit[0]["actions"][0]["set"]["units"]
                            if isinstance(v_unit, (dict, list))
                            else v_unit
                        )
                        scope_description[k_unit] = desc + " units"
                else:
                    if k in optional_other:
                        continue
                    k = (
                        f"scope_3_{scope_group}"
                        if k == f"scope_3_{scope_group}_category_other"
                        else k
                    )
                    format_key = k.replace(
                        f"{scope_group}",
                        f"{scope_group}_other",
                    )
                    key = format_key
                    scope_emissions_items[key] = scientific_to_float(v)
                    scope_description[key] = desc
                    if k.endswith("ghg") or k.endswith("co2"):
                        k_unit = key + "_units"
                        v_unit = await load_column_units(
                            k, session, static_cache
                        )
                        scope_emissions_items[k_unit] = (
                            v_unit[0]["actions"][0]["set"]["units"]
                            if isinstance(v_unit, (dict, list))
                            else v_unit
                        )
                        scope_description[k_unit] = desc + " units"
    scopes_list = [
        scope_emissions_items,
        methodology_items,
        exclusion_items,
        scope_description,
        methodology_description,
        exclusion_description,
    ]
    for scope in scopes_list:
        keys_to_remove = [key for key in scope if key.endswith("category")]
        for key in keys_to_remove:
            scope.pop(key, None)
    return (
        scope_emissions_items,
        methodology_items,
        exclusion_items,
        scope_description,
        methodology_description,
        exclusion_description,
    )
