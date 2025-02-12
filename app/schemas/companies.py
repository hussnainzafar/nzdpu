"""Companies schema"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.organization import (
    OrganizationGet,
    OrganizationGetWithNonLeiIdentifiers,
)

from .submission import SubmissionGetWithRestatedFields
from ..db.types import NullTypeState


class CompaniesGet(BaseModel):
    """
    Schema for get companies
    """

    id: int
    source: Optional[str] = None
    latest_reported_year: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class CompaniesListElementParent(CompaniesGet):
    alias: Optional[str] = None
    is_alias_match: Optional[bool] = None
    model_config = ConfigDict(from_attributes=True)


class CompaniesListElement(OrganizationGet, CompaniesListElementParent):
    """
    Schema for get companies from organizations and companies
    """


class CompaniesListElementWithNonLeiIdentifiers(
    OrganizationGetWithNonLeiIdentifiers, CompaniesListElementParent
):
    """
    Schema for get companies from organizations and companies with non lei identifiers
    """


class CompaniesSpecificCriteriaList(BaseModel):
    """
    Schema for list of companies by specific criteria
    """

    start: int
    end: int
    total: int
    items: list[CompaniesListElement | OrganizationGetWithNonLeiIdentifiers]


class MostRecentYear(BaseModel):
    """
    Schema for most recent year
    """

    most_recent_year: int


class GeneralRequirements(BaseModel):
    """
    Schema for general requirements
    """

    date_start_reporting_year: list[str]
    date_end_reporting_year: list[str]


class Disclosure(BaseModel):
    """
    Schema for disclosure
    """

    submission_id: int
    year: int
    model: str
    last_updated: datetime


class CompanyDisclosures(BaseModel):
    """
    Schema for company disclosures
    """

    start: int
    end: int
    total: int
    nz_id: int
    items: list[Disclosure]


class EmissionData(BaseModel):
    """
    Schema for emissions data
    """

    total_tco2e: list[float]
    total_tco2: list[float]


class GHG(BaseModel):
    """
    Schema for GHG
    """

    ghg_gas: int
    ghg_emissions: float
    ghg_units: int


class Values(BaseModel):
    company_name: str
    current_date: str
    reporting_year: int
    organizational_boundary: int
    methodology_used: list[Optional[str]]
    breakdown_scope1_ghg: list[GHG]


class HistoryItem(BaseModel):
    """
    Schema for history item
    """

    reporting_year: int
    submission: SubmissionGetWithRestatedFields


class CompanyEmissions(BaseModel):
    """
    Schema for company emissions
    """

    nz_id: int
    model: Optional[str] = None
    source: Optional[int] = None
    history: list[HistoryItem]


class DisclosureSortByEnum(str, Enum):
    """
    Enum for "sort_by" parameter in disclosure endpoint.
    """

    MOST_RECENT_YEAR = "most_recent_year"
    LEAST_RECENT_YEAR = "least_recent_year"


class Target(BaseModel):
    category: str
    id: str
    name: Optional[str] = None
    target_base_year: Optional[int] = None
    target_year_set: int | Optional[float] = None
    target_coverage_scope: Optional[str] = None
    active: Optional[bool] = None
    last_updated: datetime | None = None
    position: int


class TargetBySource(BaseModel):
    source: str
    items: list[Target]


class TargetsResponse(BaseModel):
    targets: list[TargetBySource]


class ReportingYearsResponse(BaseModel):
    reporting_years: list[int]


class JurisdictionsResponse(BaseModel):
    jurisdictions: list[str]


class DataSourcesResponse(BaseModel):
    data_sources: list[str]


class DataModelListResponse(BaseModel):
    id: int
    name: str
    table_view_id: int


class DataModelsResponse(BaseModel):
    data_models: list[DataModelListResponse]


class TargetsProgressSingleResponse(BaseModel):
    targets_progress: dict


class TargetsProgressResponse(BaseModel):
    targets_progress: list[dict]


class TargetValidationData(BaseModel):
    value: Optional[int | str | NullTypeState] = None
    last_updated: datetime
    last_source: str


class TargetCategory(Enum):
    ABSOLUTE = "absolute"
    INTENSITY = "intensity"


class TargetsValidationSchema(BaseModel):
    category: TargetCategory
    source: str
    last_update: Optional[datetime] = None
    reporting_year: int
    restated: Optional[bool] = None
    originally_created_on: Optional[datetime] = None
    values: Optional[dict[str, TargetValidationData]] = None


class CompanyRestatementsResponseModel(BaseModel):
    name: Optional[str] = None
    fields: list[str]


class TargetData(BaseModel):
    value: Optional[str | int | float] = None
    last_update: datetime
    last_source: str


class AbsTargetCoverageSectorList(BaseModel):
    tgt_abs_coverage_sector_name: Optional[TargetData] = None
    tgt_abs_coverage_sector_code: Optional[TargetData] = None


class AbsProgressAbsoluteTarget(BaseModel):
    tgt_abs_progress_year: Optional[TargetData] = None
    tgt_abs_s1: Optional[TargetData] = None
    tgt_abs_s2: Optional[TargetData] = None
    tgt_abs_s1s2: Optional[TargetData] = None
    tgt_abs_s3_c1: Optional[TargetData] = None
    tgt_abs_s3_c2: Optional[TargetData] = None
    tgt_abs_s3_c3: Optional[TargetData] = None
    tgt_abs_s3_c4: Optional[TargetData] = None
    tgt_abs_s3_c5: Optional[TargetData] = None
    tgt_abs_s3_c6: Optional[TargetData] = None
    tgt_abs_s3_c7: Optional[TargetData] = None
    tgt_abs_s3_c8: Optional[TargetData] = None
    tgt_abs_s3_c9: Optional[TargetData] = None
    tgt_abs_s3_c10: Optional[TargetData] = None
    tgt_abs_s3_c11: Optional[TargetData] = None
    tgt_abs_s3_c12: Optional[TargetData] = None
    tgt_abs_s3_c13: Optional[TargetData] = None
    tgt_abs_s3_c14: Optional[TargetData] = None
    tgt_abs_s3_c15: Optional[TargetData] = None
    tgt_abs_s3: Optional[TargetData] = None
    tgt_abs_total: Optional[TargetData] = None
    tgt_abs_progress_perc: Optional[TargetData] = None
    tgt_abs_reduct_perc_s1: Optional[TargetData] = None
    tgt_abs_reduct_perc_s2: Optional[TargetData] = None
    tgt_abs_reduct_perc_s1s2: Optional[TargetData] = None
    tgt_abs_reduct_perc_s3_c1: Optional[TargetData] = None
    tgt_abs_reduct_perc_s3_c2: Optional[TargetData] = None
    tgt_abs_reduct_perc_s3_c3: Optional[TargetData] = None
    tgt_abs_reduct_perc_s3_c4: Optional[TargetData] = None
    tgt_abs_reduct_perc_s3_c5: Optional[TargetData] = None
    tgt_abs_reduct_perc_s3_c6: Optional[TargetData] = None
    tgt_abs_reduct_perc_s3_c7: Optional[TargetData] = None
    tgt_abs_reduct_perc_s3_c8: Optional[TargetData] = None
    tgt_abs_reduct_perc_s3_c9: Optional[TargetData] = None
    tgt_abs_reduct_perc_s3_c10: Optional[TargetData] = None
    tgt_abs_reduct_perc_s3_c11: Optional[TargetData] = None
    tgt_abs_reduct_perc_s3_c12: Optional[TargetData] = None
    tgt_abs_reduct_perc_s3_c13: Optional[TargetData] = None
    tgt_abs_reduct_perc_s3_c14: Optional[TargetData] = None
    tgt_abs_reduct_perc_s3_c15: Optional[TargetData] = None
    tgt_abs_reduct_perc_s3: Optional[TargetData] = None
    tgt_abs_reduct_perc_total: Optional[TargetData] = None


class AbsoluteDataModel(BaseModel):
    data_source: str
    reporting_year: int
    tgt_abs_id: Optional[str] = None
    tgt_abs_name: Optional[TargetData] = None
    tgt_abs_status: Optional[TargetData] = None
    tgt_abs_status_if_inactive: Optional[TargetData] = None
    tgt_abs_year_set: Optional[TargetData] = None
    tgt_abs_type: Optional[TargetData] = None
    tgt_abs_org_boundary: Optional[TargetData] = None
    tgt_abs_cvg_scope: Optional[TargetData] = None
    tgt_abs_cvg_s3_cat: Optional[TargetData] = None
    tgt_abs_cvg_ghg: Optional[TargetData] = None
    tgt_abs_cvg_sector_approach: Optional[TargetData] = None
    tgt_abs_cvg_sector: Optional[TargetData] = None
    tgt_abs_cvg_desc: Optional[TargetData] = None
    tgt_abs_base_year_s1_perc: Optional[TargetData] = None
    tgt_abs_base_year_s2_perc: Optional[TargetData] = None
    tgt_abs_base_year_s1s2_perc: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c1_perc: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c2_perc: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c3_perc: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c4_perc: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c5_perc: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c6_perc: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c7_perc: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c8_perc: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c9_perc: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c10_perc: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c11_perc: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c12_perc: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c13_perc: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c14_perc: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c15_perc: Optional[TargetData] = None
    tgt_abs_base_year_s3_perc: Optional[TargetData] = None
    tgt_abs_base_year_total_perc: Optional[TargetData] = None
    tgt_abs_s1_emissions_units: Optional[TargetData] = None
    tgt_abs_s2_emissions_units: Optional[TargetData] = None
    tgt_abs_s1s2_emissions_units: Optional[TargetData] = None
    tgt_abs_s3_ghgp_c1_emissions_units: Optional[TargetData] = None
    tgt_abs_s3_ghgp_c2_emissions_units: Optional[TargetData] = None
    tgt_abs_s3_ghgp_c3_emissions_units: Optional[TargetData] = None
    tgt_abs_s3_ghgp_c4_emissions_units: Optional[TargetData] = None
    tgt_abs_s3_ghgp_c5_emissions_units: Optional[TargetData] = None
    tgt_abs_s3_ghgp_c6_emissions_units: Optional[TargetData] = None
    tgt_abs_s3_ghgp_c7_emissions_units: Optional[TargetData] = None
    tgt_abs_s3_ghgp_c8_emissions_units: Optional[TargetData] = None
    tgt_abs_s3_ghgp_c9_emissions_units: Optional[TargetData] = None
    tgt_abs_s3_ghgp_c10_emissions_units: Optional[TargetData] = None
    tgt_abs_s3_ghgp_c11_emissions_units: Optional[TargetData] = None
    tgt_abs_s3_ghgp_c12_emissions_units: Optional[TargetData] = None
    tgt_abs_s3_ghgp_c13_emissions_units: Optional[TargetData] = None
    tgt_abs_s3_ghgp_c14_emissions_units: Optional[TargetData] = None
    tgt_abs_s3_ghgp_c15_emissions_units: Optional[TargetData] = None
    tgt_abs_s3_emissions_units: Optional[TargetData] = None
    tgt_abs_total_emissions_units: Optional[TargetData] = None
    tgt_abs_base_year: Optional[TargetData] = None
    tgt_abs_base_year_s1_emissions: Optional[TargetData] = None
    tgt_abs_base_year_s2_emissions: Optional[TargetData] = None
    tgt_abs_base_year_s1s2_emissions: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c1_emissions: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c2_emissions: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c3_emissions: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c4_emissions: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c5_emissions: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c6_emissions: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c7_emissions: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c8_emissions: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c9_emissions: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c10_emissions: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c11_emissions: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c12_emissions: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c13_emissions: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c14_emissions: Optional[TargetData] = None
    tgt_abs_base_year_s3_ghgp_c15_emissions: Optional[TargetData] = None
    tgt_abs_base_year_s3_emissions: Optional[TargetData] = None
    tgt_abs_base_year_total_emissions: Optional[TargetData] = None
    tgt_abs_target_year: Optional[TargetData] = None
    tgt_abs_target_year_s1_emissions: Optional[TargetData] = None
    tgt_abs_target_year_s2_emissions: Optional[TargetData] = None
    tgt_abs_target_year_s1s2_emissions: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c1_emissions: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c2_emissions: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c3_emissions: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c4_emissions: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c5_emissions: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c6_emissions: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c7_emissions: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c8_emissions: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c9_emissions: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c10_emissions: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c11_emissions: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c12_emissions: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c13_emissions: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c14_emissions: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c15_emissions: Optional[TargetData] = None
    tgt_abs_target_year_s3_emissions: Optional[TargetData] = None
    tgt_abs_target_year_total_emissions: Optional[TargetData] = None
    tgt_abs_target_year_s1_perc_reduction: Optional[TargetData] = None
    tgt_abs_target_year_s2_perc_reduction: Optional[TargetData] = None
    tgt_abs_target_year_s1s2_perc_reduction: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c1_perc_reduction: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c2_perc_reduction: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c3_perc_reduction: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c4_perc_reduction: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c5_perc_reduction: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c6_perc_reduction: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c7_perc_reduction: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c8_perc_reduction: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c9_perc_reduction: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c10_perc_reduction: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c11_perc_reduction: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c12_perc_reduction: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c13_perc_reduction: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c14_perc_reduction: Optional[TargetData] = None
    tgt_abs_target_year_s3_ghgp_c15_perc_reduction: Optional[TargetData] = None
    tgt_abs_target_year_s3_perc_reduction: Optional[TargetData] = None
    tgt_abs_target_year_total_perc_reduction: Optional[TargetData] = None
    tgt_abs_ambition: Optional[TargetData] = None
    tgt_abs_method: Optional[TargetData] = None
    tgt_abs_method_desc: Optional[TargetData] = None
    tgt_abs_calc_desc: Optional[TargetData] = None
    tgt_abs_achieve_within_vc_desc: Optional[TargetData] = None
    tgt_abs_achieve_within_vc_perc: Optional[TargetData] = None
    tgt_abs_use_of_carbon_credits: Optional[TargetData] = None
    tgt_abs_use_of_carbon_credits_desc: Optional[TargetData] = None
    tgt_abs_use_of_carbon_credits_perc: Optional[TargetData] = None
    tgt_abs_achieve_other_desc: Optional[TargetData] = None


class AbsoluteDataModelWrapper(BaseModel):
    tgt_abs_dict: Optional[AbsoluteDataModel | dict] = Field(default={})
    units: dict = Field(default={})


class IntensityDataModel(BaseModel):
    data_source: str
    reporting_year: int
    tgt_int_id: Optional[str] = None
    tgt_int_name: Optional[TargetData] = None
    tgt_int_status: Optional[TargetData] = None
    tgt_int_status_if_inactive: Optional[TargetData] = None
    tgt_int_year_set: Optional[TargetData] = None
    tgt_int_type: Optional[TargetData] = None
    tgt_int_intensity_type: Optional[TargetData] = None
    tgt_int_desc: Optional[TargetData] = None
    tgt_int_org_boundary: Optional[TargetData] = None
    tgt_int_cvg_scope: Optional[TargetData] = None
    tgt_int_cvg_s3_cat: Optional[TargetData] = None
    tgt_int_cvg_ghg: Optional[TargetData] = None
    tgt_int_cvg_sector_approach: Optional[TargetData] = None
    tgt_int_cvg_sector: Optional[TargetData] = None
    tgt_int_cvg_desc: Optional[TargetData] = None
    tgt_int_base_year_s1_perc: Optional[TargetData] = None
    tgt_int_base_year_s2_perc: Optional[TargetData] = None
    tgt_int_base_year_s1s2_perc: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c1_perc: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c2_perc: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c3_perc: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c4_perc: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c5_perc: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c6_perc: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c7_perc: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c8_perc: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c9_perc: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c10_perc: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c11_perc: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c12_perc: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c13_perc: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c14_perc: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c15_perc: Optional[TargetData] = None
    tgt_int_base_year_s3_perc: Optional[TargetData] = None
    tgt_int_base_year_total_perc: Optional[TargetData] = None
    tgt_int_units: Optional[TargetData] = None
    tgt_int_units_usd: Optional[TargetData] = None
    tgt_int_units_num: Optional[TargetData] = None
    tgt_int_units_denom: Optional[TargetData] = None
    tgt_int_units_denom_usd: Optional[TargetData] = None
    tgt_int_base_year: Optional[TargetData] = None
    tgt_int_base_year_activity_metric: Optional[TargetData] = None
    tgt_int_base_year_activity_metric_usd: Optional[TargetData] = None
    tgt_int_base_year_s1_int: Optional[TargetData] = None
    tgt_int_base_year_s2_int: Optional[TargetData] = None
    tgt_int_base_year_s1s2_int: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c1_int: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c2_int: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c3_int: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c4_int: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c5_int: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c6_int: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c7_int: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c8_int: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c9_int: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c10_int: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c11_int: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c12_int: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c13_int: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c14_int: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c15_int: Optional[TargetData] = None
    tgt_int_base_year_s3_int: Optional[TargetData] = None
    tgt_int_base_year_total_int: Optional[TargetData] = None
    tgt_int_base_year_s1_int_usd: Optional[TargetData] = None
    tgt_int_base_year_s2_int_usd: Optional[TargetData] = None
    tgt_int_base_year_s1s2_int_usd: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c1_int_usd: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c2_int_usd: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c3_int_usd: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c4_int_usd: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c5_int_usd: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c6_int_usd: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c7_int_usd: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c8_int_usd: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c9_int_usd: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c10_int_usd: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c11_int_usd: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c12_int_usd: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c13_int_usd: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c14_int_usd: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c15_int_usd: Optional[TargetData] = None
    tgt_int_base_year_s3_int_usd: Optional[TargetData] = None
    tgt_int_base_year_total_int_usd: Optional[TargetData] = None
    tgt_int_base_year_s1_emissions: Optional[TargetData] = None
    tgt_int_base_year_s2_emissions: Optional[TargetData] = None
    tgt_int_base_year_s1s2_emissions: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c1_emissions: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c2_emissions: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c3_emissions: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c4_emissions: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c5_emissions: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c6_emissions: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c7_emissions: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c8_emissions: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c9_emissions: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c10_emissions: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c11_emissions: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c12_emissions: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c13_emissions: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c14_emissions: Optional[TargetData] = None
    tgt_int_base_year_s3_ghgp_c15_emissions: Optional[TargetData] = None
    tgt_int_base_year_s3_emissions: Optional[TargetData] = None
    tgt_int_base_year_total_emissions: Optional[TargetData] = None
    tgt_int_target_year: Optional[TargetData] = None
    tgt_int_target_year_s1_int: Optional[TargetData] = None
    tgt_int_target_year_s2_int: Optional[TargetData] = None
    tgt_int_target_year_s1s2_int: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c1_int: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c2_int: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c3_int: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c4_int: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c5_int: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c6_int: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c7_int: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c8_int: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c9_int: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c10_int: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c11_int: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c12_int: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c13_int: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c14_int: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c15_int: Optional[TargetData] = None
    tgt_int_target_year_s3_int: Optional[TargetData] = None
    tgt_int_target_year_total_int: Optional[TargetData] = None
    tgt_int_target_year_s1_int_usd: Optional[TargetData] = None
    tgt_int_target_year_s2_int_usd: Optional[TargetData] = None
    tgt_int_target_year_s1s2_int_usd: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c1_int_usd: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c2_int_usd: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c3_int_usd: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c4_int_usd: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c5_int_usd: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c6_int_usd: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c7_int_usd: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c8_int_usd: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c9_int_usd: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c10_int_usd: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c11_int_usd: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c12_int_usd: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c13_int_usd: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c14_int_usd: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c15_int_usd: Optional[TargetData] = None
    tgt_int_target_year_s3_int_usd: Optional[TargetData] = None
    tgt_int_target_year_total_int_usd: Optional[TargetData] = None
    tgt_int_target_year_s1_int_perc_reduction: Optional[TargetData] = None
    tgt_int_target_year_s2_int_perc_reduction: Optional[TargetData] = None
    tgt_int_target_year_s1s2_int_perc_reduction: Optional[TargetData] = None
    tgt_int_target_year_s3_ghgp_c1_int_perc_reduction: Optional[TargetData] = (
        None
    )
    tgt_int_target_year_s3_ghgp_c2_int_perc_reduction: Optional[TargetData] = (
        None
    )
    tgt_int_target_year_s3_ghgp_c3_int_perc_reduction: Optional[TargetData] = (
        None
    )
    tgt_int_target_year_s3_ghgp_c4_int_perc_reduction: Optional[TargetData] = (
        None
    )
    tgt_int_target_year_s3_ghgp_c5_int_perc_reduction: Optional[TargetData] = (
        None
    )
    tgt_int_target_year_s3_ghgp_c6_int_perc_reduction: Optional[TargetData] = (
        None
    )
    tgt_int_target_year_s3_ghgp_c7_int_perc_reduction: Optional[TargetData] = (
        None
    )
    tgt_int_target_year_s3_ghgp_c8_int_perc_reduction: Optional[TargetData] = (
        None
    )
    tgt_int_target_year_s3_ghgp_c9_int_perc_reduction: Optional[TargetData] = (
        None
    )
    tgt_int_target_year_s3_ghgp_c10_int_perc_reduction: Optional[
        TargetData
    ] = None
    tgt_int_target_year_s3_ghgp_c11_int_perc_reduction: Optional[
        TargetData
    ] = None
    tgt_int_target_year_s3_ghgp_c12_int_perc_reduction: Optional[
        TargetData
    ] = None
    tgt_int_target_year_s3_ghgp_c13_int_perc_reduction: Optional[
        TargetData
    ] = None
    tgt_int_target_year_s3_ghgp_c14_int_perc_reduction: Optional[
        TargetData
    ] = None
    tgt_int_target_year_s3_ghgp_c15_int_perc_reduction: Optional[
        TargetData
    ] = None
    tgt_int_target_year_s3_int_perc_reduction: Optional[TargetData] = None
    tgt_int_target_year_total_int_perc_reduction: Optional[TargetData] = None
    tgt_int_ambition: Optional[TargetData] = None
    tgt_int_method: Optional[TargetData] = None
    tgt_int_method_desc: Optional[TargetData] = None
    tgt_int_calc_desc: Optional[TargetData] = None
    tgt_int_achieve_within_vc_desc: Optional[TargetData] = None
    tgt_int_achieve_within_vc_perc: Optional[TargetData] = None
    tgt_int_use_of_carbon_credits: Optional[TargetData] = None
    tgt_int_use_of_carbon_credits_desc: Optional[TargetData] = None
    tgt_int_use_of_carbon_credits_perc: Optional[TargetData] = None
    tgt_int_achieve_other_desc: Optional[TargetData] = None


class IntensityDataModelWrapper(BaseModel):
    tgt_int_dict: Optional[IntensityDataModel | dict] = Field(default={})
    units: dict = Field(default={})


class GetTargetById(BaseModel):
    """GetTargetById _summary_

    :param _type_ BaseModel: _description_
    """

    absolute: Optional[AbsoluteDataModelWrapper] = None
    intensity: Optional[IntensityDataModelWrapper] = None
