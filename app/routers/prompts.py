"""Prompts router"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from starlette import status

from app.db.models import AttributePrompt, AuthRole
from app.dependencies import DbManager, RoleAuthorization, oauth2_scheme
from app.schemas.prompt import (
    AttributePromptCreate,
    AttributePromptGet,
    AttributePromptUpdate,
    PaginationResponse,
)

from .utils import check_admin_access_rights, update_user_data_last_accessed

# pylint: disable = not-callable

# creates the router
router = APIRouter(
    prefix="/schema/prompts",
    tags=["prompts"],
    dependencies=[Depends(oauth2_scheme)],
    responses={404: {"description": "Not found"}},
)


@router.get("", response_model=PaginationResponse)
async def list_prompts(
    db_manager: DbManager,
    filter_by: str | None = None,
    order_by: str | None = None,
    order: str = "asc",
    start: int = 0,
    limit: int = 1000,
    current_user=Depends(
        RoleAuthorization(
            [
                AuthRole.DATA_PUBLISHER,
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ]
        )
    ),
):
    """
    Return the list of configured prompts

    Parameters
    ----------
        filter_by - filter as dict e.g. {"column_def_id":"1"} (or {"column_def_id":1})
        order_by - list of ordering fields e.g. ["value","id"]
        order - default "asc", can apply "asc" and "desc"
        start - starting index
        limit - number of records to return

    Returns
    -------
        dict with start, end, total and items keys
    """
    # verify order param
    if order not in ["asc", "desc"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid order value {order}. Must be 'asc or 'desc'",
        )

    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # parse the filter_by and order_by parameters
        filter_dict = {}
        order_by_list = []
        if filter_by:
            try:
                filter_dict = json.loads(filter_by)
                # print(filter_dict)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Invalid filter_by format. Must be a valid JSON"
                        " string."
                    ),
                ) from exc
        if order_by:
            try:
                order_by_list = json.loads(order_by)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Invalid order_by format. Must be a valid JSON list of"
                        " strings."
                    ),
                ) from exc
        # load attribute prompts
        query = select(AttributePrompt).offset(start).limit(limit)
        # apply filtering from filter_by query params
        if "column_def_id" in filter_dict:
            try:
                column_def_id = int(
                    filter_dict["column_def_id"]
                )  # Convert to integer
                query = query.where(
                    AttributePrompt.column_def_id == column_def_id
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Invalid value for 'column_def_id'. Must be an"
                        " integer."
                    ),
                ) from exc
        if "value" in filter_dict:
            query = query.where(
                AttributePrompt.value.ilike(f"%{filter_dict['value']}%")
            )

        # order by query parameter
        for field in order_by_list:
            if field == "id":
                query = query.order_by(
                    AttributePrompt.id.asc()
                    if order == "asc"
                    else AttributePrompt.id.desc()
                )
            elif field == "column_def_id":
                query = query.order_by(
                    AttributePrompt.column_def_id.asc()
                    if order == "asc"
                    else AttributePrompt.column_def_id.desc()
                )
            elif field == "value":
                query = query.order_by(
                    AttributePrompt.value.asc()
                    if order == "asc"
                    else AttributePrompt.value.desc()
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Invalid order_by value {field}."
                        " Must be id, column_def_id, value."
                    ),
                )
        result = await _session.execute(query)
        records = result.scalars().all()

        # Get total number of records
        total_stmt = select(func.count()).select_from(AttributePrompt)
        total_result = await _session.execute(total_stmt)
        total = total_result.scalar_one()

    # Prepare response
    response = {
        "start": start,
        "end": start + len(records),
        "total": total,
        "items": records,
    }

    return response


@router.post("", response_model=AttributePromptGet)
async def create_prompt(
    prompt: AttributePromptCreate,
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization(
            [
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ]
        )
    ),
):
    """
    Create a new prompt

    Parameters
    ----------
        prompt - prompt input data
    Returns
    -------
        the new prompt
    """

    db_prompt = AttributePrompt(**prompt.model_dump())
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # check admin access rights
        await check_admin_access_rights(
            session=_session, current_user=current_user
        )

        _session.add(db_prompt)
        await _session.commit()
    return db_prompt


@router.get("/{prompt_id}", response_model=AttributePromptGet)
async def get_prompt(
    prompt_id: int,
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization(
            [
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ]
        )
    ),
):
    """
    Return the details of an attribute prompt

    Parameters
    ----------
        prompt_id - prompt identifier
    Returns
    -------
        prompt data
    """

    # load prompt
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        db_prompt = await _session.get(AttributePrompt, prompt_id)
        if db_prompt is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"prompt_id": "Attribute prompt not found"},
            )

    return db_prompt


@router.patch("/{prompt_id}", response_model=AttributePromptGet)
async def update_prompt(
    prompt_id: int,
    prompt: AttributePromptUpdate,
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization(
            [
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ]
        )
    ),
):
    """
    Update an existing attribute prompt

    Parameters
    ----------
        prompt_id - identifier of the prompt record we want to update
        prompt - prompt input data
    Returns
    -------
        the updated attribute prompt
    """

    # load prompt
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # check admin access rights
        await check_admin_access_rights(
            session=_session, current_user=current_user
        )

        db_prompt = await _session.get(AttributePrompt, prompt_id)
        if db_prompt is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"prompt_id": "Prompt not found"},
            )

        # update attributes sent by the client
        prompt_data = prompt.model_dump(exclude_unset=True)
        for key, value in prompt_data.items():
            setattr(db_prompt, key, value)
        # save updated prompt
        _session.add(db_prompt)
        await _session.commit()
    return db_prompt
