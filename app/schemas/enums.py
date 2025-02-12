"""
Enums used in schemas.
"""

from enum import Enum, StrEnum
from typing import Any, Generic, TypeVar

T = TypeVar("T", str, Any)


class EnumValuesTrait(Generic[T]):
    @classmethod
    def values(cls: Enum) -> list[T]:
        return [v.value for v in cls]


class SortOrderEnum(StrEnum):
    """
    Enums for sorting order.
    """

    ASC = "asc"
    DESC = "desc"


class SubmissionObjStatusEnum(StrEnum):
    """
    Submission object status column enum.
    """

    DRAFT = "draft"
    PUBLISHED = "published"
    BLANK = "blank"


class SICSSectorEnum(StrEnum):
    TECHNOLOGY_COMMUNICATIONS = "Technology & Communications"
    FOOD_BEVERAGE = "Food & Beverage"
    EXTRACTIVES_MINERALS_PROCESSING = "Extractives & Minerals Processing"
    HEALTH_CARE = "Health Care"
    FINANCIALS = "Financials"
    RENEWABLE_RESOURCES_ALTERNATIVE_ENERGY = (
        "Renewable Resources & Alternative Energy"
    )
    CONSUMER_GOODS = "Consumer Goods"
    TRANSPORTATION = "Transportation"
    INFRASTRUCTURE = "Infrastructure"
    RESOURCE_TRANSFORMATION = "Resource Transformation"
    SERVICES = "Services"
    NOT_CLASSIFIED = "Not Classified by SICS"


e = "emissions"


class EmissionsUnitsEnum(
    EnumValuesTrait[str],
    StrEnum,
):
    """
    Emissions fields where units are present enum.
    """

    EMISSIONS = f"{e}"
    EMISSIONS_GHG = f"{e}_ghg"
    EMISSIONS_CO2 = f"{e}_co2"
    FE_AUM_CO2 = f"{e}_aum_co2"
    FE_AUM_GHG = f"{e}_aum_ghg"
    FE_GE_GHG = f"{e}_grossexp_ghg"
    FE_GE_CO2 = f"{e}_grossexp_co2"


class DefaultPromptsEnum(
    EnumValuesTrait[str],
    StrEnum,
):
    """
    Default prompts for export enum.
    """

    LEGAL_NAME = "Organization Legal Name"
    JURISDICTION = "Jurisdiction"
    LEI = "Legal Entity Identifier (LEI)"
    SICS_SECTOR = "SICS Sector"
    SICS_SUB_SECTOR = "SICS Sub-Sector"
    SICS_INDUSTRY = "SICS Industry"
