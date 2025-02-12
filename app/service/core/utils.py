"""
Utils class module for submission manager.
"""

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ColumnDef
from app.schemas.column_def import AttributeType
from app.utils import reflect_form_table


async def load_attribute_type(
    attr_name: str, session: AsyncSession
) -> AttributeType:
    """
    Given attribute name, returns the attribute type from DB

    Parameters
    ----------
        attr_name - name identifier
    Returns
    -------
        attribute type
    """
    # load group
    result = await session.execute(
        select(ColumnDef).where(ColumnDef.name == attr_name)
    )
    attr_type = result.scalars().first()
    if attr_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "attr_type": (
                    "No column definitions found for the given attribute name!"
                )
            },
        )

    return attr_type.attribute_type


async def update_form_with_null_values(
    submission_id: int,
    key_list: list,
    value: str,
    length: int,
    session: AsyncSession,
) -> None:
    """
    Update attributes in the table based on the provided dictionary using raw SQL.

    Parameters:
    - table_name: The name of the table to update.
    - submission_id: The ID of the submission to update.
    - update_dict: A dictionary containing the attributes to
        update as keys and their new values as values.
    - session: The database session.

    Returns:
    - None.
    """
    if length == 3:
        sub_form = f"{key_list[0]}_form_heritable"
        sub_form_index = int(key_list[1])
        attr = key_list[2]
        # select IDs from sub_form into list
        sub_form_table = await reflect_form_table(session, sub_form)
        sql_select_query = (
            select(sub_form_table.c.id)
            .where(sub_form_table.c.obj_id == submission_id)
            .order_by(sub_form_table.c.id)
        )
        query_select_form = await session.execute(sql_select_query)

        ids_list = query_select_form.scalars().all()
        # update specific sub_form attribute
        sql_update_query = (
            update(sub_form_table)
            .where(sub_form_table.c.obj_id == submission_id)
            .where(sub_form_table.c.id == ids_list[sub_form_index])
            .where(sub_form_table.c[attr] == None)
            .values({attr: value})
        )
        await session.execute(sql_update_query)
        await session.commit()
    elif length == 5:
        sub_form = f"{key_list[0]}_form_heritable"
        sub_form_index = int(key_list[1])
        sub_sub_form = f"{key_list[2]}_form_heritable"
        sub_sub_form_index = int(key_list[3])
        attr = key_list[4]
        sub_form_table = await reflect_form_table(session, sub_form)
        sub_sub_form_table = await reflect_form_table(session, sub_sub_form)

        # select IDs from sub_form into list
        sql_select_query = (
            select(sub_sub_form_table.c.id)
            .distinct()
            .join(
                sub_form_table,
                sub_sub_form_table.c.obj_id == sub_form_table.c.obj_id,
            )
            .where(sub_sub_form_table.c.obj_id == submission_id)
            .order_by(sub_sub_form_table.c.id)
        )
        query_select_form = await session.execute(sql_select_query)

        ids_list = query_select_form.scalars().all()

        # update specific sub_form attribute
        sql_update_query = (
            update(sub_sub_form_table)
            .where(sub_sub_form_table.c.obj_id == submission_id)
            .where(sub_sub_form_table.c.id == ids_list[sub_sub_form_index])
            .where(sub_sub_form_table.c[attr] == None)
            .values({attr: value})
        )
        await session.execute(sql_update_query)
        await session.commit()
    elif length == 7:
        sub_form = f"{key_list[0]}_form_heritable"
        sub_form_index = int(key_list[1])
        sub_sub_form = f"{key_list[2]}_form_heritable"
        sub_sub_form_index = int(key_list[3])
        sub_sub_sub_form = f"{key_list[4]}_form_heritable"
        sub_sub_sub_index = int(key_list[5])
        attr = key_list[6]
        # select IDs from sub_form into list

        sub_form_table = await reflect_form_table(session, sub_form)
        sub_sub_form_table = await reflect_form_table(session, sub_sub_form)
        sub_sub_sub_form_table = await reflect_form_table(
            session, sub_sub_sub_form
        )

        sql_select_query = (
            select(sub_sub_sub_form_table.c.id)
            .join(
                sub_sub_form_table,
                sub_sub_sub_form_table.c.obj_id == sub_sub_form_table.c.obj_id,
            )
            .join(
                sub_form_table,
                sub_sub_sub_form_table.c.obj_id == sub_form_table.c.obj_id,
            )
            .where(sub_sub_sub_form_table.c.obj_id == submission_id)
            .order_by(sub_sub_sub_form_table.c.id)
            .distinct()
        )
        query_select_form = await session.execute(sql_select_query)

        ids_list = query_select_form.scalars().all()
        # update specific sub_form attribute
        sql_update_query = (
            update(sub_sub_sub_form_table)
            .where(sub_sub_sub_form_table.c.obj_id == submission_id)
            .where(sub_sub_sub_form_table.c.id == ids_list[sub_sub_sub_index])
            .where(sub_sub_sub_form_table.c[attr].is_(None))
            .values({attr: value})
        )
        await session.execute(sql_update_query)
        await session.commit()
    elif length == 1:
        form = "nzdpu_form"
        attr = key_list[0]
        # update specific sub_form attribute
        form_table = await reflect_form_table(session, form)
        sql_update_query = (
            update(form_table)
            .where(form_table.c.obj_id == submission_id)
            .where(form_table.c[attr].is_(None))
            .values({attr: value})
        )
        await session.execute(sql_update_query)
        await session.commit()


def strip_none(data):
    """
    Recursively strips None valued fields from a nested Python dict.

    Args:
        data (dict): A nested Python dictionary.

    Returns:
        dict: The Python dict, stripped of None valued fields.
    """
    if isinstance(data, dict):
        return {
            k: strip_none(v)
            for k, v in data.items()
            if k is not None
            and v is not None
            and k not in ["id", "obj_id", "value_id"]
        }
    if isinstance(data, list):
        return [strip_none(item) for item in data if item is not None]
    if isinstance(data, tuple):
        return tuple(strip_none(item) for item in data if item is not None)
    if isinstance(data, set):
        return {strip_none(item) for item in data if item is not None}
    return data
