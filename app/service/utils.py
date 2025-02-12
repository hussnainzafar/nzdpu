from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ColumnDef, ColumnView
from app.db.types import NullTypeState
from app.service.core.cache import CoreMemoryCache


async def load_column_units(
    column_name: str, session: AsyncSession, static_cache: CoreMemoryCache
) -> list[dict[str, Any]] | str:
    """
    Given column name, returns the corresponding record from the
    DB.

    Parameters
    ----------
        column_name - column name

    Returns
    -------
        column units from contraint value
    """
    column_defs = await static_cache.column_defs_by_name()
    column = column_defs.get(column_name)
    constraint_value = None
    if column and column.views:
        if column.views[0].constraint_value:
            constraint_value = column.views[0].constraint_value
    else:
        result = await session.execute(
            select(ColumnView.constraint_value)
            .join(ColumnDef, ColumnDef.id == ColumnView.column_def_id)
            .filter(ColumnDef.name == column_name)
        )
        constraint_value = result.scalars().first()
    if constraint_value is None or len(constraint_value) == 0:
        return ""

    return constraint_value


async def format_units(
    values: dict,
    field: str,
    session: AsyncSession,
    static_cache: CoreMemoryCache,
    parent_values: dict = None,
):
    """
    Given values and field returns the corresponding unit
    DB.

    Parameters
    ----------
        values - values from form
        field - specific field which we need to pull unit from

    Returns
    -------
        formatted unit
    """
    v_unit = await load_column_units(field, session, static_cache)
    if v_unit:
        try:
            v_unit = v_unit[0]["actions"][0]["set"]["units"]
        except KeyError:
            return None
        if v_unit.startswith("{") and v_unit.endswith("}"):
            v_unit_key = v_unit.strip("{}")
            # check if field is not in form values and use parent values
            v_unit = (
                parent_values.get(v_unit_key)
                if v_unit_key not in values
                else values.get(v_unit_key)
            )
    return v_unit if v_unit and v_unit not in NullTypeState.values() else None


# Dictionary mapping subscript Unicode characters to normal characters
subscript_to_normal = {
    "\u2080": "0",
    "\u2081": "1",
    "\u2082": "2",
    "\u2083": "3",
    "\u2084": "4",
    "\u2085": "5",
    "\u2086": "6",
    "\u2087": "7",
    "\u2088": "8",
    "\u2089": "9",
    "\u2090": "a",
    "\u2091": "e",
    "\u2092": "o",
    "\u2093": "x",
    "\u2094": "schwa",
    "\u2095": "h",
    "\u2096": "k",
    "\u2097": "l",
    "\u2098": "m",
    "\u2099": "n",
    "\u209a": "p",
    "\u209b": "s",
    "\u209c": "t",
}


def transform_subscript_to_normal(text: str | None) -> str:
    if text is None or not isinstance(text, str):
        return text

    # Replace each subscript character with its normal equivalent
    for subscript, normal in subscript_to_normal.items():
        text = text.replace(subscript, normal)
    return text


def parse_and_transform_subscripts_to_normal(data):
    """Recursively parse and transform strings in dictionaries, lists, or objects."""
    if isinstance(data, dict):
        return {
            key: parse_and_transform_subscripts_to_normal(value)
            for key, value in data.items()
        }
    elif isinstance(data, list):
        return [
            parse_and_transform_subscripts_to_normal(element)
            for element in data
        ]
    elif isinstance(data, str):
        return transform_subscript_to_normal(data)
    else:
        return data
