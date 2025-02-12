"""Module for search API schemas"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List

from pydantic import BaseModel, BeforeValidator

from .enums import SICSSectorEnum, SortOrderEnum

# pylint: disable = too-few-public-methods


def _sort_fields_to_dict(
    v: str | dict[str, SearchDSLSortOptions],
) -> dict[str, SearchDSLSortOptions]:
    """
    When the sort field in the request is a string, transforms the
    value to a dict made of the field as key, and the default
    ascending order (`{"order": "asc"}`) as value.

    E.g.:
    `"string"`
    becomes
    `{"string": {"order": "asc"}}`

    Args:
        v (str | dict[str, dict[str, SortOrderEnum]]): The value.

    Raises:
        ValueError: If a value of invalid type is passed (pre=True).

    Returns:
        dict[str, SearchDSLSortOptions]: The correct structure for
            the value.
    """
    if isinstance(v, str):
        return {v: SearchDSLSortOptions(order=SortOrderEnum.ASC)}
    if isinstance(v, dict):
        return v
    raise ValueError("'sort' section only supports strings or objects.")


class SearchDSLMetaElement(BaseModel):
    """
    Schema for meta section of search API.
    """

    reporting_year: list[int] = []
    data_model: list[str] = []
    jurisdiction: list[str] = []
    sics_sector: list[str] = []
    sics_sub_sector: list[str] = []
    sics_industry: list[str] = []


class SearchResponse(BaseModel):
    """
    Schema for Search API response.
    """

    start: int
    size: int
    total_disclosures: int
    total_companies: int
    items: List[Dict[str, Any]]


class SearchResponseItem(BaseModel):
    """
    Schema for Search API response items element.
    """

    legal_name: str
    lei: str
    resporting_year: int
    jurisdiction: str
    data_model: str
    sics_sector: SICSSectorEnum
    sics_sub_sector: str
    sics_industry: str


class SearchDSLSortOptions(BaseModel):
    """
    Schema for options of sort element.
    """

    order: SortOrderEnum


class SearchDSLStatement(BaseModel):
    """
    Schema for Search DSL raw SQL query statement
    """

    select: list[str] = []
    from_: list[str] = []
    join: list[str] = []
    where: list[str] = []
    sort: list[str] = []
    limit: list[str] = []
    offset: list[str] = []


ValidSort = Annotated[
    str | dict[str, SearchDSLSortOptions],
    BeforeValidator(_sort_fields_to_dict),
]


class SearchQuery(BaseModel):
    """
    Schema for Search API request body.
    """

    sort: list[ValidSort] = []
    meta: SearchDSLMetaElement = SearchDSLMetaElement()
    fields: list[str] = []


class DownloadExceedResponse(BaseModel):
    companies_count: int
    error_message: str
