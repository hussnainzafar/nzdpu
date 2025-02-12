"""Exports headers."""

import json
from enum import Enum
from pathlib import Path

from app import settings

data_dir: Path = settings.BASE_DIR.parent / "app/service/exports/headers"


class ExportOptions(str, Enum):
    """
    Enums for download options.
    """

    COMPANIES = "companies"
    SEARCH = "search"


class CompaniesSheets(str, Enum):
    """
    Enums for companies sheet names.
    """

    company_metadata = "Company Metadata"
    main_sheet = "Emissions"
    financed_emissions_sheet = "Financed Emissions (Scope 3)"
    assure_verif = "Assurance & Verification"
    restatement_sheet = "Restatements"
    emissions_reduction_targets = "Emissions Reduction Targets"
    targets_progress_sheet = "Target Progress"
    validation_sheet = "Target Validation"


class SearchSheets(str, Enum):
    """
    Enums for search sheet names.
    """

    KEY = "KEY"
    METADATA = "METADATA"
    SCOPE_1_EMISSIONS_SHEET = "SCOPE 1 EMISSIONS"
    SCOPE_1_GHG_BREAKDOWN_SHEET = "SCOPE 1 GHG BREAKDOWN"
    SCOPE_1_EXCLUSIONS_SHEET = "SCOPE 1 EXCLUSIONS"
    SCOPE_2_LB_EMISSIONS_SHEET = "SCOPE 2 LB EMISSIONS"
    SCOPE_2_LB_EXCLUSIONS_SHEET = "SCOPE 2 LB EXCLUSIONS"
    SCOPE_2_MB_EMISSIONS_SHEET = "SCOPE 2 MB EMISSIONS"
    SCOPE_2_MB_EXCLUSIONS_SHEET = "SCOPE 2 MB EXCLUSIONS"
    SCOPE_3_EMISSIONS_SHEET = "SCOPE 3 EMISSIONS"
    SCOPE_3_METHODOLOGY_SHEET = "SCOPE 3 METHODOLOGY"
    SCOPE_3_EXCLUSIONS_SHEET = "SCOPE 3 EXCLUSIONS"
    FE_OVERVIEW_AUM_SHEET = "FIN EMISSIONS OV (AUM)"
    FE_ABSOLUTE_AUM_SHEET = "ABSOLUTE FIN EMISSIONS (AUM)"
    FE_INTENSITY_AUM_SHEET = "FIN EMISSIONS INTENSITY (AUM)"
    FE_DATA_QUALITY_AUM_SHEET = "FIN EMISSIONS DQ (AUM)"
    FE_OVERVIEW_GE_SHEET = "FIN EMISSIONS OV (GROSS EXP)"
    FE_ABSOLUTE_GE_SHEET = "ABS FIN EMISSIONS (GROSS EXP)"
    FE_INTENSITY_GE_SHEET = "FIN EMISSIONS INT (GROSS EXP)"
    FE_DATA_QUALITY_GE_SHEET = "FIN EMISSIONS DQ (GROSS EXP)"
    AV_EMISSIONS_SHEET = "A&V EMISSIONS"
    AV_TARGETS_SHEET = "TARGET VALIDATION"
    RESTATEMENTS_EMISSIONS_SHEET = "RESTATEMENTS (EMISSIONS)"
    RESTATEMENTS_TARGETS_SHEET = "RESTATEMENTS (TARGETS)"
    TARGETS_ABSOLUTE_SHEET = "TARGETS (ABSOLUTE)"
    TARGETS_PROGRESS_ABSOLUTE_SHEET = "TARGET PROGRESS (ABSOLUTE)"
    TARGETS_INTENSITY_PHYS_SHEET = "TARGETS (PHYS INTENSITY)"
    TARGETS_PROGRESS_PHYS_INTENSITY_SHEET = "TARGET PROGRESS (PHYS INTENSITY"
    TARGETS_INTENSITY_ECON_SHEET = "TARGETS (ECON INTENSITY)"
    TARGETS_PROGRESS_ECON_INTENSITY_SHEET = "TARGET PROGRESS (ECON INTENSITY"


def get_data_explorer_headers(worksheet_name: str) -> dict:
    """
    Map on provided worksheet name returns default headers
    """
    with open(
        data_dir / "data_explorer_headers.json", encoding="utf-8"
    ) as headers_json:
        default_headers = json.load(headers_json)
        headers = default_headers.get(worksheet_name, None)
    return headers


def get_companies_headers(worksheet_name: str) -> dict:
    """
    Map on provided worksheet name returns default headers
    """
    with open(
        data_dir / "companies_headers.json", encoding="utf-8"
    ) as headers_json:
        default_headers = json.load(headers_json)
        headers = default_headers.get(worksheet_name, None)
    return headers


def get_default_attributes_for_v40(
    worksheet_name: str, value: str | None
) -> dict:
    """
    Map on provided worksheet name returns default headers
    """
    with open(data_dir / "default_attributes_v40.json") as headers_json:
        default_headers = json.load(headers_json)
        headers = default_headers.get(worksheet_name, None)
        if value is None:
            headers = replace_dash_with_none(headers)
    return headers


def replace_dash_with_none(headers):
    """
    Recursively replace all instances of '-' with None in the given data structure.
    """
    if isinstance(headers, dict):
        return {
            key: replace_dash_with_none(value)
            for key, value in headers.items()
        }
    elif isinstance(headers, list):
        return [replace_dash_with_none(item) for item in headers]
    elif headers == "-":
        return None
    return headers
