"""Utility functions for routers"""

import re
from datetime import datetime
from decimal import Decimal
from enum import Enum
from functools import wraps
from typing import Any

from fastapi import Depends, HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from unidecode import unidecode

from app.service.core.cache import CoreMemoryCache
from app.service.core.loaders import SubmissionLoader

from ..db.models import (
    Choice,
    ColumnDef,
    ColumnView,
    Group,
    Organization,
    OrganizationAlias,
    PasswordHistory,
    Permission,
    Restatement,
    SourceEnum,
    SubmissionObj,
    TableDef,
    TableView,
    Tracking,
    User,
)
from ..dependencies import DbManager, get_current_user
from ..forms.form_meta import FormMeta
from ..loggers import get_nzdpu_logger
from ..schemas.restatements import (
    AttributePathsModel,
    RestatementList,
    RestatementOriginal,
)
from ..schemas.tracking import TrackingCreate, TrackingUrls
from ..service.access_manager import AccessManager
from ..service.utils import format_units, load_column_units
from ..utils import check_password, encrypt_password, reflect_form_table

logger = get_nzdpu_logger()


# pylint: disable = unsupported-binary-operation, not-callable


class ErrorMessage(str, Enum):
    """
    Error messages.
    """

    ATTRIBUTE_NOT_FOUND_MESSAGE = "Attribute not found."
    ATTRIBUTE_NOT_IN_TABLE_DEF_MESSAGE = (
        "The requested attribute is not associated with this table definition."
    )
    ATTRIBUTE_VIEW_NOT_FOUND_MESSAGE = "Attribute view not found."
    ORGANIZATION_NOT_FOUND = "No organization matches the given LEI."
    DUPLICATED_ATTRIBUTE = "Duplicated attribute."
    GROUP_NOT_FOUND_MESSAGE = "Group not found."
    PERMISSION_NOT_FOUND_MESSAGE = "Permission not found."
    TABLE_DEF_EXISTS = "Table definition already exists."
    TABLE_DEF_NOT_FOUND_MESSAGE = "Table definition not found."
    TABLE_VIEW_NOT_FOUND_MESSAGE = "Table view not found."
    TABLE_VIEW_NOT_ACTIVE_MESSAGE = (
        "Cannot accept a submission on a non-active view."
    )
    NO_ASSOCIATED_TABLE_VIEW_MESSAGE = (
        "No active associated table view available for this table definition."
    )
    TABLE_VIEW_REVISION_NOT_FOUND_MESSAGE = "Table view revision not found."
    USER_NOT_FOUND_MESSAGE = "User not found."
    USER_DOES_NOT_HAVE_PERMISSION = (
        "User does not have permission to perform this operation."
    )
    EMAIL_ADDRESS_REQUIRED = "Email address is required."
    ID_DOES_NOT_BELONG_TO_FIREBASE_USER = (
        "The provided ID does not belong to Firebase user."
    )
    EMAIL_DOES_NOT_BELONG_TO_FIREBASE_USER = (
        "The provided email address does not belong to any Firebase user."
    )
    FIREBASE_PASSWORD_DOES_NOT_MATCH = (
        "The current password does not match with firebase password."
    )
    PASSWORD_DOES_NOT_MATCH = (
        "The current password does not match with the password from the"
        " database."
    )
    CHOICE_EXISTS = "Choice already exists."
    CHOICE_NOT_FOUND = "Choice not found."
    FILE_NOT_FOUND = "File not found."
    NOT_ALLOWED = "You don't have permission for this action."


async def load_attribute(
    attribute_id: int, session: AsyncSession
) -> ColumnDef:
    """
    Given an attribute ID, returns the corresponding record from the DB

    Parameters
    ----------
        attribute_id - attribute identifier
    Returns
    -------
        attribute data
    """
    # load attribute
    attribute = await session.get(ColumnDef, attribute_id)
    if attribute is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"attribute_id": ErrorMessage.ATTRIBUTE_NOT_FOUND_MESSAGE},
        )

    return attribute


async def load_attribute_view(
    attribute_view_id: int, session: AsyncSession
) -> ColumnView:
    """
    Given an attibute view ID, returns the corresponding record from the
    DB.

    Parameters
    ----------
        attribute_view_id - attribute view identifier

    Returns
    -------
        the attribute view
    """
    # load attribute view
    attribute_view = await session.get(ColumnView, attribute_view_id)
    if attribute_view is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "attribute_view_id": (
                    ErrorMessage.ATTRIBUTE_VIEW_NOT_FOUND_MESSAGE
                )
            },
        )

    return attribute_view


async def get_choice_value(choice_id, session, static_cache) -> int | str:
    """
    Return choice_value for column_name
    """
    if not isinstance(choice_id, bool) and isinstance(choice_id, int):
        choices = await static_cache.choices()
        choice_res = choices.get(choice_id)
        if not choice_res:
            choice = await session.execute(
                select(Choice).where(Choice.choice_id == choice_id)
            )
            choice_res = choice.scalars().first()
        if choice_res is None:
            return choice_id
        return choice_res.value
    return choice_id


async def get_value_from_computed_units(attribute: str, computed_units: dict):
    """
    Recursively search for the value associated with
    the given attribute in a nested dictionary or list.

    Parameters
    ----------
        attribute - attribute for search unit
        computed_units - dict of computed units

    Returns
    -------
        attribute value from computed units
    """
    if isinstance(computed_units, dict):
        # if it's a dictionary, check if the attribute is present
        if attribute in computed_units:
            return computed_units[attribute]
        # if not found, recursively search through the values in the dictionary
        for key, value in computed_units.items():
            result = await get_value_from_computed_units(attribute, value)
            if result is not None:
                return result
    elif isinstance(computed_units, list):
        # if it's a list, recursively search through the elements in the list
        for item in computed_units:
            result = await get_value_from_computed_units(attribute, item)
            if result is not None:
                return result

        # If the attribute is not found, return None
    return None


async def process_other_unit(
    sub_form: str,
    obj_id: int,
    field_id: int,
    field: str,
    session: AsyncSession,
    static_cache: CoreMemoryCache,
):
    """
    Given params, returns the corresponding record from the
    DB.

    Parameters
    ----------
        sub_form - sub-form from field
        comparison - field for comparison of sub form
        field - field of sub form
        where - field for select where

    Returns
    -------
        choice value from unit
    """
    sub_form_field_other = await reflect_form_table(
        session, f"{sub_form}.{field}_other"
    )
    sub_form_table = await static_cache.get_form_table(sub_form)
    sql_select_query = select(sub_form_field_other).where(
        sub_form_table.c.obj_id == obj_id, sub_form_table.c.id == field_id
    )

    query_select_form = await session.execute(sql_select_query)
    dynamic_units = query_select_form.scalars().first()
    unit = (
        await get_choice_value(dynamic_units, session, static_cache)
        if isinstance(dynamic_units, int)
        else dynamic_units
    )
    return unit


async def load_dynamic_units(
    obj_id: int,
    field_id: int,
    field: str,
    session: AsyncSession,
    static_cache: CoreMemoryCache,
) -> str | None:
    """
    Given sub_form and id, returns the corresponding record from the
    DB.

    Parameters
    ----------
        comparison - field for comparison of sub form
        field - field of sub form
        where - field for select where

    Returns
    -------
        choice value from unit
    """
    not_computed_unit = None
    if not field.endswith("}"):
        if "/" in field:
            not_computed_unit = field.rsplit("}")[-1]
            field = field.replace(not_computed_unit, "")
        else:
            not_computed_unit = field.rsplit("}")[-1]
            field = field.rsplit(" ")[0]
    pattern = r"\{([^\}]+)\}"

    field_names = re.findall(pattern, field)

    if len(field_names) == 1:
        column_defs = await static_cache.column_defs_by_name()
        result = column_defs.get(field[1:-1])
        sub_form = result.table_def.name
        if sub_form is not None and sub_form != "nzdpu_form":
            sub_form += "_heritable"
        sub_form_table = await static_cache.get_form_table(sub_form)
        sql_query = select(getattr(sub_form_table.c, field[1:-1])).where(
            sub_form_table.c.obj_id == obj_id,
        )
        if sub_form != "nzdpu_form":
            sql_query = sql_query.where(sub_form_table.c.id == field_id)
        query_select_form = await session.execute(sql_query)
        dynamic_units = query_select_form.scalars().first()
        if dynamic_units is None:
            sql_query = select(getattr(sub_form_table.c, field[1:-1])).where(
                sub_form_table.c.obj_id == obj_id,
            )
            query_select_form = await session.execute(sql_query)
            dynamic_units = query_select_form.scalars().first()
        unit = (
            await get_choice_value(dynamic_units, session, static_cache)
            if isinstance(dynamic_units, int)
            else dynamic_units
        )
        if unit == "Other not listed":
            unit = await process_other_unit(
                sub_form, obj_id, field_id, field[1:-1], session, static_cache
            )
        if not_computed_unit and isinstance(unit, str):
            unit += not_computed_unit
        return unit
    else:
        unit_list = []
        for f in field_names:
            result = await session.execute(
                select(TableDef.name)
                .join(ColumnDef, ColumnDef.table_def_id == TableDef.id)
                .filter(ColumnDef.name == f)
            )
            sub_form = result.scalars().first()
            if sub_form is not None and sub_form != "nzdpu_form":
                sub_form += "_heritable"
            sub_form_table = await reflect_form_table(session, sub_form)
            sql_query = select(getattr(sub_form_table.c, f)).where(
                sub_form_table.c.obj_id == obj_id,
            )
            if sub_form != "nzdpu_form":
                sql_query = sql_query.where(sub_form_table.c.id == field_id)
            query_select_form = await session.execute(sql_query)

            dynamic_units = query_select_form.scalars().first()
            if dynamic_units is None:
                sql_select_query = select(getattr(sub_form_table.c, f)).where(
                    sub_form_table.c.obj_id == obj_id
                )
                query_select_form = await session.execute(sql_select_query)
                dynamic_units = query_select_form.scalars().first()
            unit = (
                await get_choice_value(dynamic_units, session, static_cache)
                if isinstance(dynamic_units, int)
                else dynamic_units
            )
            if unit == "Other not listed":
                unit = await process_other_unit(
                    sub_form, obj_id, field_id, f, session, static_cache
                )
            unit_list.append(str(unit))
        if len(field_names) == 3:
            unit_res = (
                " / ".join(unit_list[:2]) + " " + " ".join(unit_list[2:])
            )
        else:
            if "/" in field:
                unit_res = " / ".join(unit_list)
            else:
                unit_res = " ".join(unit_list)
        if not_computed_unit:
            unit_res += not_computed_unit
        if "None / None" in unit_res:
            unit_res = unit_res.replace("None / None", "").strip()
            if unit_res == "":
                return None
        return unit_res


async def load_choice_values_from_set_id(
    set_id, session: AsyncSession
) -> list[str]:
    """
    Given choice set_id, returns the corresponding list of record from the
    DB.

    Parameters
    ----------
        set_id - choice set identifier

    Returns
    -------
        list of choice
    """
    # load choice by set id
    result = await session.execute(
        select(Choice.value).where(Choice.set_id == set_id)
    )
    choice = list(result.scalars().all())
    if choice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"choice_id": ErrorMessage.CHOICE_NOT_FOUND},
        )

    return choice


async def load_organization_by_lei(
    lei: str, session: AsyncSession
) -> Organization:
    """
    Given an organization lei, returns the corresponding record from the
    DB.

    Parameters
    ----------
        lei - organization identifier by lei

    Returns
    -------
        organization
    """
    # load organization by lei
    result = await session.execute(
        select(Organization).where(Organization.lei == lei)
    )
    organization = result.scalars().first()
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"lei": ErrorMessage.ORGANIZATION_NOT_FOUND},
        )

    return organization


async def load_organization(
    organization_id, session: AsyncSession
) -> Organization:
    """
    Given an organization id, returns the corresponding record from the
    DB.

    Parameters
    ----------
        organization_id - organization identifier

    Returns
    -------
        organization
    """
    # load organization by lei
    result = await session.execute(
        select(Organization).where(Organization.id == organization_id)
    )
    organization = result.scalars().first()
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"organization_id": ErrorMessage.ORGANIZATION_NOT_FOUND},
        )

    return organization


async def load_user_organization(
    user_id, session: AsyncSession
) -> Organization:
    """
    Given a user id, returns the organization bound to this user.

    Parameters
    ----------
        user_id - user identifier

    Returns
    -------
        organization, or None if no organization is bound to this user
    """

    # load user
    result = await session.execute(select(User).where(User.id == user_id))

    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"global": "User not found."},
        )

    # load organization
    return await load_organization(user.organization_id, session)


async def load_column_defs(
    table_def_id: int, session: AsyncSession
) -> list[ColumnDef]:
    """
    Given a TableDef ID, retrieves all the column definitions related
    to that table definition.

    Args:
        table_def_id (int): The table definition ID.
        session (AsyncSession): The SQLAlchemy session.

    Raises:
        ValueError: No column definitions found.

    Returns:
        list[ColumnDef]: A list of column definitions.
    """
    column_defs: list[ColumnDef] = list(
        (
            await session.scalars(
                select(ColumnDef).where(ColumnDef.table_def_id == table_def_id)
            )
        )
        .unique()
        .all()
    )
    if not column_defs:
        raise ValueError(
            "No column definitions found for the given table def!"
        )

    return sorted(column_defs, key=lambda c: c.id)


async def load_group(group_id: int, session: AsyncSession) -> Group:
    """
    Given a group ID, returns the corresponding record from the DB

    Parameters
    ----------
        group_id - group identifier
    Returns
    -------
        group data
    """
    # load group
    result = await session.execute(select(Group).where(Group.id == group_id))
    group = result.scalars().first()
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"group_id": ErrorMessage.GROUP_NOT_FOUND_MESSAGE},
        )

    return group


async def load_permission(
    permission_id: int, session: AsyncSession
) -> Permission:
    """
    Given a permission ID, returns the corresponding record from the DB

    Parameters
    ----------
        permission_id - permission identifier
    Returns
    -------
        permission data
    """
    # load permission
    result = await session.execute(
        select(Permission).where(Permission.id == permission_id)
    )
    permission = result.scalars().first()
    if permission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "permission_id": ErrorMessage.PERMISSION_NOT_FOUND_MESSAGE
            },
        )

    return permission


async def load_table_def(table_def_id: int, session: AsyncSession) -> TableDef:
    """
    Given a TableDef ID, returns the corresponding record from the DB.

    Parameters
    ----------
        table_def_id - table definition identifier.

    Returns
    --------
        the table definition
    """
    table_def = await session.get(TableDef, table_def_id)
    if table_def is None:
        # return 404 on invalid (non-existing) table def ID
        raise HTTPException(
            status_code=404,
            detail={"table_def_id": ErrorMessage.TABLE_DEF_NOT_FOUND_MESSAGE},
        )

    return table_def


async def load_table_view(
    table_view_id: int, session: AsyncSession
) -> TableView:
    """
    Given a TableView ID, returns the corresponding record from the DB.

    Parameters
    ----------
        table_view_id - table view identifier.

    Returns
    -------
        the table view
    """
    table_view = await session.get(TableView, table_view_id)
    if table_view is None:
        # return 404 on invalid (non-existing) table view ID
        raise HTTPException(
            status_code=404,
            detail={
                "table_view_id": ErrorMessage.TABLE_VIEW_NOT_FOUND_MESSAGE
            },
        )

    return table_view


async def load_user(user_id: int, session: AsyncSession):
    """
    Given a user ID, returns the corresponding record from the DB

    Parameters
    ----------
        user_id - user identifier
    Returns
    -------
        user data
    """
    # load user
    result = await session.execute(
        select(User)
        .options(selectinload(User.groups))
        .where(User.id == user_id)
    )
    user = result.scalars().first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"user_id": ErrorMessage.USER_NOT_FOUND_MESSAGE},
        )

    return user


def create_cache_key(request, appendix="") -> str:
    """
    Method copied from uvicorn.protocols.utils to get path as it is
    displayed in fastAPI logs.

    Args:
        request (fastapi.Request): A FastAPI Request object.

    Returns:
        str: The path with optional query parameters.
    """
    path_with_query_string = request.url.path[1:]  # remove leading /
    if request.url.query:
        # pylint: disable = consider-using-f-string
        path_with_query_string = "{}?{}".format(
            path_with_query_string, request.url.query
        )
    return path_with_query_string + appendix


async def check_admin_access_rights(session: AsyncSession, current_user):
    """
    Checks if the current user has administrative access rights.
    """

    access_manager = AccessManager(session)
    is_admin = access_manager.is_admin(user=current_user)
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"global": ErrorMessage.USER_DOES_NOT_HAVE_PERMISSION},
        )


async def check_access_rights(
    session: AsyncSession, entity, user, access_type, error_message
):
    """
    Checks if the current user has access rights to perform operation.
    """

    access_manager = AccessManager(session)
    granted = await access_manager.can_read_write(
        entity=entity, user=user, access_type=access_type
    )
    if not granted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_message,
        )


async def get_max_choice_ids(session: AsyncSession) -> tuple[int, int]:
    """
    Return the maximum choice identifier and set identifier in the database
    Parameters
    ----------
    session: database session

    Returns
    -------
    a couple with the maximum choice ID and set ID, in this order
    """

    stmt = select(
        func.max(Choice.choice_id).label("max_choice_id"),
        func.max(Choice.set_id).label("max_set_id"),
    )
    result = await session.execute(stmt)
    row = result.first()
    max_choice_id = 0
    max_set_id = 0
    if row:
        max_choice_id = row.max_choice_id if row.max_choice_id else 0
        max_set_id = row.max_set_id if row.max_set_id else 0

    return max_choice_id, max_set_id


async def update_user_data_last_accessed(
    session: AsyncSession, current_user: User = Depends(get_current_user)
):
    """
    Updates current user's "data_last_accessed" obj
    :param current_user: current user
    :return: the updated current user
    """
    if current_user is None:
        return None
    current_user.data_last_accessed = datetime.now()
    session.add(current_user)
    await session.commit()
    return current_user.data_last_accessed


async def user_existence(user_email: str, session: AsyncSession):
    """
    Given a user ID, returns the corresponding record from the DB

    Parameters
    ----------
        user_id - user identifier
    Returns
    -------
        user data
    """
    # load user
    result = await session.execute(
        select(User)
        .options(selectinload(User.groups))
        .where(User.email == user_email)
    )
    user = result.scalars().first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"user_id": ErrorMessage.USER_NOT_FOUND_MESSAGE},
        )

    return user


async def remove_special_values_to_none(data):
    """
    Args:
    - data: The input which can be a dict, list, or other types.

    Returns:
    - Processed data with special values replaced by None.
    """
    if isinstance(data, list):
        return [await remove_special_values_to_none(item) for item in data]
    if isinstance(data, dict):
        return {
            key: await remove_special_values_to_none(value)
            for key, value in data.items()
        }
    return data


async def get_original_value(
    submission_loader: SubmissionLoader,
    submission_ids: list[int],
    attribute_path: AttributePathsModel,
    year: int | None = None,
) -> RestatementOriginal | None:
    """
    Get original value from submission where revision = 1
    """
    # get data from first submission
    submission = await submission_loader.load(
        submission_id=submission_ids[0]  # revision = 1
    )
    reporting_year = submission.values[FormMeta.f_reporting_year]

    reporting_datetime = submission.values.get(
        "reporting_datetime", submission.created_on
    )

    if year is None:
        return RestatementOriginal(
            reporting_year=reporting_year,
            reported_on=reporting_datetime,
            value=submission_loader.return_value(
                path=attribute_path, values=submission.values
            )
            or {},
            source=submission.data_source or -1,
        )
    if year == reporting_year:
        return RestatementOriginal(
            reporting_year=reporting_year,
            reported_on=reporting_datetime,
            value=submission_loader.return_value(
                path=attribute_path, values=submission.values
            )
            or {},
            source=submission.data_source or -1,
        )
    return None


def is_valid_password(password, username, is_level2=False, email=None):
    """
    Validates a password according to specific rules and returns an error message if it's invalid.

    Args:
    - password: The password to validate.
    - username: The username associated with the account.
    - is_level2: True for Level 2 accounts, False for Level 1 accounts.

    Returns:
    - If the password is valid, returns None.
    - If the password is invalid, returns an error message describing the issue.
    """

    # Check if the password is at least 12 characters long
    if len(password) < 12:
        return "Password must be at least 12 characters long."

    # Check if the password is the same as the username
    if password == username:
        return "Password must not be the same as the username."

    if password == email:
        return "Password must not be the same as the email."

    # # Define patterns that should not be present in the password
    # prohibited_patterns = [
    #     r"(\w)\1{2,}",  # Three or more consecutive repeated characters
    #     r"q[weerty]+|w[qwerty]+|e[qwerty]+|r[qwerty]+|t[qwerty]+|y[qwerty]+",  # Simple keyboard patterns
    #     r"z[xcvbnmas]+|x[zcvbnmas]+|c[xcvbnmas]+|v[xcvbnmas]+|b[xcvbnmas]+|n[xcvbnmas]+|m[xcvbnmas]+",  # Simple keyboard patterns
    #     r"(\d)\1{2,}",  # Three or more consecutive repeated digits
    # ]

    # # Check if the password contains prohibited patterns
    # for pattern in prohibited_patterns:
    #     if re.search(pattern, password, re.IGNORECASE):
    #         return "Password contains prohibited patterns."

    # Check if the password contains at least 2 of the following character classes (Level 1)
    # or at least 3 of the following character classes (Level 2)
    character_classes = 0
    if re.search(r"[A-Z]", password):
        character_classes += 1
    if re.search(r"[a-z]", password):
        character_classes += 1
    if re.search(r"\d", password):
        character_classes += 1
    if re.search(r'[!@#\$%^&*(),.?":{}|<>]', password):
        character_classes += 1

    if is_level2:
        if character_classes < 3:
            return (
                "Password should contain two of the following: "
                "uppercase letter, lowercase letter, "
                "number or punctuation marks."
            )
    else:
        if character_classes < 2:
            return (
                "Password should contain two of the following: "
                "uppercase letter, lowercase letter, "
                "number or punctuation marks."
            )

    # If none of the validation rules triggered, the password is valid
    return None


async def retrieve_user_password_history(user_id: int, session: AsyncSession):
    history_query = (
        select(PasswordHistory)
        .filter_by(user_id=user_id)
        .order_by(desc(PasswordHistory.created_on))
        .limit(5)
    )
    password_history = await session.execute(history_query)
    password_history_list = password_history.scalars().all()

    return password_history_list


async def check_password_history(
    user_id: int, new_password: str, session: AsyncSession
):
    password_history_list = await retrieve_user_password_history(
        user_id, session
    )

    # Check if the new password matches any of the recent passwords.
    for history_entry in password_history_list:
        if check_password(new_password, history_entry.encrypted_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "new_password": (
                        "The new password you entered is the same as one of"
                        " your previous five passwords. Please enter a"
                        " different password."
                    )
                },
            )


async def update_password_history(
    user_id: int, new_password: str, session: AsyncSession
):
    password_history_list = await retrieve_user_password_history(
        user_id, session
    )

    # If the password history is already at the maximum limit, replace
    # the oldest entry
    if len(password_history_list) >= 5:
        oldest_password_entry = min(
            password_history_list, key=lambda entry: entry.created_on
        )
        await session.delete(oldest_password_entry)
    # hash new password
    new_hashed_pass = encrypt_password(new_password)
    # Add the new password to the history
    new_history_entry = PasswordHistory(
        user_id=user_id, encrypted_password=new_hashed_pass
    )
    session.add(new_history_entry)

    await session.commit()


def normalize_text(input_text):
    # Use unidecode to convert Unicode text to its closest ASCII representation
    normalized_text = unidecode(input_text)
    return normalized_text


def list_of_ids_of_matched(obj, name):
    list_of_id = []

    for each in obj:
        nor_name = normalize_text(each.legal_name)
        if name.lower() in nor_name.lower():
            list_of_id.append(each.id)

    return list_of_id


def names_of_matched(obj, name):
    for each in obj:
        nor_name = normalize_text(each.legal_name)
        if name.lower() in nor_name.lower():
            return each.legal_name

    return None


async def transform_computed_units(
    original, session, static_cache, value_transformer=lambda x: x
):
    """
    Recursively process a dictionary to create a new one with specific modifications:
    - Exclude certain keys (like id, obj_id, value_id, and keys ending with 'prompt')
    - Apply a transformation function to the values (default is to keep them unchanged)
    :param original: The original dictionary to be processed
    :param session: Session
    :param value_transformer: A function to apply to each value
    :return: A new dictionary with the specified modifications
    """
    if isinstance(original, dict):
        new_dict = {}
        key_id = original.get("id", None)
        key_obj_id = original.get("obj_id", None)
        for key, value in original.items():
            if not key.endswith("prompt") and key not in [
                "id",
                "obj_id",
                "value_id",
            ]:
                if isinstance(value, list):
                    transformed_list = [
                        await transform_computed_units(
                            item, session=session, static_cache=static_cache
                        )
                        for item in value
                        if not isinstance(item, int)
                    ]
                    if transformed_list and not all(
                        isinstance(item, int) for item in transformed_list
                    ):
                        if all(
                            isinstance(item, str) for item in transformed_list
                        ):
                            v_unit = await load_column_units(
                                key, session, static_cache
                            )
                            units = None
                            if v_unit and isinstance(v_unit, list):
                                try:
                                    first_item = v_unit[0]
                                    if "actions" in first_item and isinstance(
                                        first_item["actions"], list
                                    ):
                                        first_action = first_item["actions"][0]
                                        if (
                                            "set" in first_action
                                            and isinstance(
                                                first_action["set"], dict
                                            )
                                        ):
                                            if "units" in first_action["set"]:
                                                units = first_action["set"][
                                                    "units"
                                                ]
                                                if units.startswith("{"):
                                                    units = await load_dynamic_units(
                                                        key_obj_id,
                                                        key_id,
                                                        units,
                                                        session,
                                                        static_cache,
                                                    )
                                except (IndexError, KeyError):
                                    pass
                            new_dict[key] = units
                        else:
                            new_dict[key] = transformed_list
                elif isinstance(value, dict):
                    transformed_dict = await transform_computed_units(
                        value, session=session, static_cache=static_cache
                    )
                    if transformed_dict:
                        new_dict[key] = transformed_dict
                else:
                    v_unit = await load_column_units(
                        key, session, static_cache
                    )
                    units = None
                    if v_unit and isinstance(v_unit, list):
                        try:
                            first_item = v_unit[0]
                            if "actions" in first_item and isinstance(
                                first_item["actions"], list
                            ):
                                first_action = first_item["actions"][0]
                                if "set" in first_action and isinstance(
                                    first_action["set"], dict
                                ):
                                    if "units" in first_action["set"]:
                                        units = first_action["set"]["units"]
                                        if units.startswith("{"):
                                            units = await load_dynamic_units(
                                                key_obj_id,
                                                key_id,
                                                units,
                                                session,
                                                static_cache,
                                            )
                        except (IndexError, KeyError):
                            pass
                    new_dict[key] = units
        return new_dict
    if isinstance(original, list):
        return [
            await transform_computed_units(
                item, session=session, static_cache=static_cache
            )
            for item in original
            if not isinstance(item, int)
        ]
    return value_transformer(original)


async def get_restated_fields_data_source(
    submission_name: str, session: AsyncSession
) -> dict[str, int]:
    """Returns dictionary of restated fields to data source"""

    stmt = (
        select(Restatement.attribute_name, Restatement.data_source)
        .join(SubmissionObj, SubmissionObj.id == Restatement.obj_id)
        .order_by(SubmissionObj.id.asc())
        .where(SubmissionObj.name == submission_name)
    )

    results = (await session.execute(stmt)).all()

    restated_fields_data_source = {}

    for attribute_name, data_source in results:
        restated_fields_data_source[attribute_name] = data_source

    return restated_fields_data_source


async def get_restated_list_data_source_and_last_updated(
    submission_name: str,
    session: AsyncSession,
    only_last_attribute: bool = False,
) -> dict:
    """Returns dictionary of restated fields with list of
    data source and last updated"""

    stmt = (
        select(
            Restatement.attribute_name,
            Restatement.data_source,
            Restatement.reporting_datetime,
        )
        .join(SubmissionObj, SubmissionObj.id == Restatement.obj_id)
        .where(SubmissionObj.name == submission_name)
        .order_by(SubmissionObj.id.asc())
    )

    results = (await session.execute(stmt)).all()

    restated_fields_data_source = {}

    for attribute_name, data_source, last_updated in results:
        if only_last_attribute:
            # restatements are hold with whole path, we need only the last attribute name
            splitted = attribute_name.split(".")
            if len(splitted) > 0:
                key = splitted[-1]
                restated_fields_data_source[key] = (
                    data_source,
                    last_updated,
                )
        else:
            restated_fields_data_source[attribute_name] = (
                data_source,
                last_updated,
            )

    return restated_fields_data_source


def check_fields_limit(query_fields: list[str]):
    """
    Strips the default fields from the total selected fields count.
    Raises 422 if fields count is over limit.
    """

    default_fields = {"legal_name", "reporting_year", "data_model"}

    if len(set(query_fields) - default_fields) > 35:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="too many fields in request",
        )


async def get_updated_user_name_if_same_with_mail(name: str, email: str):
    """
    return split name if same as email
    """

    if name == email:
        return email.split("@")[0]
    return name


def is_string_ascii_only(string: str):
    """returns true if string is ascii only, otherwise false

    Args:
        string (str): string to check

    Returns:
        bool: true if string is ascii only, otherwise false
    """
    return re.search(r"^[\x00-\x7F]+$", string) is not None


async def process_restatements(
    submission_loader: SubmissionLoader,
    db_restatements: list[Restatement],
    attribute_path: AttributePathsModel,
    year: int | None = None,
):
    """
    Process restatements
    """
    restatements = []
    restatement: Restatement
    for restatement in db_restatements:
        submission = await submission_loader.load(
            submission_id=restatement.obj_id,
        )
        reporting_year = submission.values[FormMeta.f_reporting_year]

        if year and year == reporting_year:
            restatements.append(
                RestatementList(
                    reporting_year=reporting_year,
                    reported_on=restatement.reporting_datetime,
                    value=submission_loader.return_value(
                        attribute_path, submission.values
                    )
                    or {},
                    reason=restatement.reason_for_restatement or "",
                    disclosure_source=restatement.data_source or "",
                )
            )

    return restatements


async def get_expanded_name(name: str, session: AsyncSession):
    """
    Returns expanded (full) name of organization through alias
    """
    result = await session.execute(
        select(OrganizationAlias).where(OrganizationAlias.alias == name)
    )
    alias_record = result.scalars().first()
    if not alias_record:
        return name
    return alias_record.legal_name


async def process_target_progress_categories(
    targets_root,
    progres_values,
    data_source,
    target_key,
    session,
    static_cache,
    last_updated=None,
    attribute_name_last_update_dict=None,
    attribute_name_last_source_dict=None,
):
    progress_dict = {}
    progress_dict_units = {}
    if isinstance(progres_values, dict):
        static_data = {"data_source": data_source}
        static_data.update({"target_id": progres_values.get(target_key)})
        for k, v in progres_values.items():
            if k in ["id", "obj_id", "value_id", target_key] or k.endswith(
                "_prompt"
            ):
                continue
            try:
                progress_dict[k] = (
                    (
                        v
                        if k in ["data_source", "reporting_year"]
                        else {
                            "value": v,
                            "last_update": (
                                attribute_name_last_update_dict.get(k)
                                if isinstance(
                                    attribute_name_last_update_dict, dict
                                )
                                and k in attribute_name_last_update_dict
                                and attribute_name_last_update_dict.get(k)
                                else last_updated
                            ),
                            "last_source": (
                                attribute_name_last_source_dict.get(k)
                                if isinstance(
                                    attribute_name_last_source_dict, dict
                                )
                                and k in attribute_name_last_source_dict
                                and attribute_name_last_source_dict.get(k)
                                else data_source
                            ),
                        }
                    )
                    if last_updated
                    else v
                )
                progress_dict_units[k] = await format_units(
                    targets_root, k, session, static_cache
                )
            except Exception as e:
                logger.error(
                    f"Error processing key {k}, value {v}, attribute_name_last_source_dict: {attribute_name_last_source_dict}, attribute_name_last_update_dict: {attribute_name_last_update_dict}, last_updated: {last_updated}: {e}"
                )
                raise
        progress_dict.update({"units": progress_dict_units})
        progress_dict.update(static_data)
    return progress_dict


def track_api_usage(api_endpoint: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            results = await func(*args, **kwargs)
            db_manager: DbManager = kwargs.get("db_manager")
            current_user: User = kwargs.get("current_user")
            nz_id: int | None = kwargs.get("nz_id", None)
            api_endpoint_format = None
            lei: str | None = kwargs.get("lei", None)
            if lei:
                api_endpoint_format = TrackingUrls.COMPANIES_HISTORY.format(
                    nz_id=lei
                )

            if nz_id:
                api_endpoint_format = TrackingUrls.COMPANIES_HISTORY.format(
                    nz_id=nz_id
                )
            async with db_manager.get_session() as _session:
                tracking_schema = TrackingCreate(
                    user_email=(
                        current_user.email if current_user.email else ""
                    ),
                    api_endpoint=(
                        api_endpoint_format
                        if api_endpoint_format
                        else api_endpoint
                    ),
                    source=SourceEnum.WEB.value,
                    result=status.HTTP_200_OK,
                )
                new_tracking = Tracking(**tracking_schema.model_dump())
                _session.add(new_tracking)
                await _session.commit()

                return results

        return wrapper

    return decorator


def scientific_to_float(sci_str: Any) -> str:
    """
    Converts a string in scientific notation or regular numeric form to a floating-point number using `Decimal`.
    Ensures no scientific notation and retains full precision.

    Parameters:
        sci_str (str): The string representation of the number in scientific notation or numeric form.

    Returns:
        float: The floating-point representation of the number.
        If the input is invalid, raises InvalidOperation.
    """
    if isinstance(sci_str, int):
        return str(sci_str)

    if isinstance(sci_str, float):
        try:
            # Use Decimal to handle arbitrary precision and avoid scientific notation
            decimal_value = Decimal(str(sci_str))
            value = format(decimal_value, "f")

            return value
        except Exception:
            # Raise an error if the string cannot be converted to a Decimal
            return str(sci_str)

    return str(sci_str)
