"""Choices router"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.db.models import AuthRole, Choice
from app.dependencies import DbManager, RoleAuthorization
from app.schemas.choice import (
    ChoiceCreate,
    ChoiceCreateSet,
    ChoiceCreateSetResponse,
    ChoiceGet,
    ChoiceSetPaginationResponse,
    ChoiceSetResponse,
    ChoiceUpdate,
    PaginationResponse,
)

from .utils import (
    ErrorMessage,
    get_max_choice_ids,
    update_user_data_last_accessed,
)

# creates the router
router = APIRouter(
    prefix="/schema/choices",
    tags=["choices"],
    # dependencies=[Depends(oauth2_scheme)],
    responses={404: {"description": "Not found"}},
)


@router.get("", response_model=PaginationResponse)
async def list_choices(
    db_manager: DbManager,
    filter_by: str | None = None,
    order_by: str | None = None,
    order: str = "asc",
    limit: int = 1000,
    start: int = 0,
):
    """
    Return the list of configured choices

    Parameters
    ----------
        filter_by - filter as dict e.g. {"set_id":"1"} (or {"set_id":1})
        order_by - list of ordering fields e.g. ["value","id"]
        order - default "asc", can apply "asc" and "desc"
        limit - number of records to return
        start - starting record index

    Returns
    -------
        dict with start, end, total and items keys
    """

    _session: AsyncSession
    async with db_manager.get_session() as _session:
        # parse the filter_by and order_by parameters
        filter_dict = {}
        order_by_list = []
        if filter_by:
            try:
                filter_dict = json.loads(filter_by)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "filter_by": (
                            "Invalid filter_by format."
                            " Must be a valid JSON string."
                        )
                    },
                ) from exc
        if order_by:
            try:
                order_by_list = json.loads(order_by)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "order_by": (
                            "Invalid order_by format."
                            " Must be a valid JSON list of strings."
                        )
                    },
                ) from exc
        # load choices
        query = select(Choice).offset(start).limit(limit)
        # apply filtering from filter_by query params
        if "choice_id" in filter_dict:
            try:
                choice_id = int(filter_dict["choice_id"])  # Convert to integer
                query = query.where(Choice.choice_id == choice_id)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"choice_id": "Must be an integer."},
                ) from exc
        if "set_id" in filter_dict:
            try:
                set_id = int(filter_dict["set_id"])  # Convert to integer
                query = query.where(Choice.set_id == set_id)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"set_id": "Must be an integer."},
                ) from exc
        if "value" in filter_dict:
            query = query.where(
                Choice.value.ilike(f"%{filter_dict['value']}%")
            )

        # order by query parameter
        for field in order_by_list:
            if field == "id":
                query = query.order_by(
                    Choice.id.asc() if order == "asc" else Choice.id.desc()
                )
            elif field == "choice_id":
                query = query.order_by(
                    Choice.choice_id.asc()
                    if order == "asc"
                    else Choice.choice_id.desc()
                )
            elif field == "set_id":
                query = query.order_by(
                    Choice.set_id.asc()
                    if order == "asc"
                    else Choice.set_id.desc()
                )
            elif field == "value":
                query = query.order_by(
                    Choice.value.asc()
                    if order == "asc"
                    else Choice.value.desc()
                )
            elif field == "order":
                query = query.order_by(
                    Choice.order.asc()
                    if order == "asc"
                    else Choice.order.desc()
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Invalid order_by value {field}."
                        " Must be id, choice_id, set_id, value, or order"
                    ),
                )
        result = await _session.execute(query)
        records = result.scalars().all()

        # Get total number of records
        total_stmt = select(func.count()).select_from(Choice)  # pylint: disable=not-callable
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


@router.post("", response_model=ChoiceGet)
async def create_choice(
    choice: ChoiceCreate,
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
    Create a new choice

    Parameters
    ----------
        choice - choice input data
    Returns
    -------
        the new choice
    """

    _session: AsyncSession
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        max_set_id = None
        if not choice.choice_id:
            # set choice id
            max_choice_id, max_set_id = await get_max_choice_ids(_session)
            choice.choice_id = max(
                max_choice_id + 1 if max_choice_id else 1,
                Choice.CHOICE_ID_AUTO_START,
            )
        # look for existing set_name
        result = await _session.execute(
            select(Choice.set_id).where(Choice.set_name == choice.set_name)
        )
        existing_record = result.first()

        if existing_record:
            # if set_name already exists
            if choice.set_id and choice.set_id != existing_record[0]:
                # if set_id is provided but doesn't match with the existing record
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "choice.set_id": (
                            (
                                "Provided set_id doesn't match with the"
                                " existing record. Please remove set_id from"
                                " the request or provide the existing set_id."
                            ),
                        )
                    },
                )
            # use the set_id from the existing record
            choice.set_id = existing_record[0]
        else:
            # if set_name doesn't exist, generate a new set_id
            choice.set_id = max_set_id + 1 if max_set_id else 1

        # look for duplicate choices
        result = await _session.execute(
            select(Choice)
            .where(Choice.choice_id == choice.choice_id)
            .where(Choice.set_id == choice.set_id)
            .where(Choice.set_name == choice.set_name)
            .where(Choice.language_code == choice.language_code)
        )
        if result.first():
            # duplicated table
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"choice": ErrorMessage.CHOICE_EXISTS},
            )

        # create choice
        db_choice = Choice(**choice.model_dump())
        _session.add(db_choice)
        await _session.commit()

    return db_choice


@router.post("/set", response_model=ChoiceCreateSetResponse)
async def create_choice_set(
    choice_set: ChoiceCreateSet,
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
    Parameters
    ----------
    choice_set - data of the choice set to create
    session - database session

    Returns
    -------
    identifier of the new set
    """

    _session: AsyncSession
    # get current max values
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # look for existing set_name
        result = await _session.execute(
            select(Choice.set_id).where(Choice.set_name == choice_set.set_name)
        )
        existing_record = result.first()

        if existing_record:
            # if set_name already exists and set_id is provided in request body but does not match
            set_id = existing_record[0]
        else:
            # if set_name does not exist in db, assign set_id as max_set_id from db
            _, max_set_id = await get_max_choice_ids(_session)
            set_id = max_set_id + 1 if max_set_id else 1

        max_choice_id, _ = await get_max_choice_ids(_session)

    choice_id = max(
        max_choice_id + 1 if max_choice_id else 1, Choice.CHOICE_ID_AUTO_START
    )
    rank = 1

    db_choices: list[Choice] = []
    for label in choice_set.labels:
        # create choice
        db_choices.append(
            Choice(
                choice_id=choice_id,
                set_id=set_id,
                set_name=choice_set.set_name,
                value=label,
                order=rank,
                language_code=choice_set.language_code,
            )
        )
        choice_id = choice_id + 1
        rank = rank + 1

    # create choice set
    async with db_manager.get_session() as _session:
        _session.add_all(db_choices)
        # commit transaction
        await _session.commit()

    return {"set_id": set_id}


@router.get("/sets", response_model=ChoiceSetPaginationResponse)
async def list_choice_sets(
    db_manager: DbManager,
    limit: int = 1000,
    start: int = 0,
):
    """
    Return the list of configured choice sets and their choices

    Parameters
    ----------
        limit - number of records to return
        start - starting record index

    Returns
    -------
        dict with start, end, total and items keys
    """
    conditional_set_id = limit + start if start == 0 else limit + start - 1
    # load choice sets
    stmt = select(Choice).where(
        (Choice.set_id >= start) & (Choice.set_id <= conditional_set_id)
    )
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        result = await _session.execute(stmt)
        records = result.scalars().all()

        # Get total number of records
        # pylint: disable=not-callable
        total_count = await _session.scalar(
            func.count(func.distinct(Choice.set_id))
        )

        # Group choices by set_id
        grouped_records = {}
        list_of_set_id = []
        for record in records:
            if record.set_id not in grouped_records:
                grouped_records[record.set_id] = {
                    "set_id": record.set_id,
                    "set_name": record.set_name,
                    "choices": [],
                }
            choice = {
                key: value
                for key, value in record.__dict__.items()
                if key not in ["set_id", "set_name"]
                # Exclude set_name here
            }
            grouped_records[record.set_id]["choices"].append(choice)
            if record.set_id not in list_of_set_id:
                list_of_set_id.append(record.set_id)

    # Prepare response
    response = {
        "start": start,
        "end": (
            (len(list_of_set_id) + start)
            if start == 0
            else len(list_of_set_id) + start - 1
        ),
        "total": total_count,
        "items": list(grouped_records.values()),
    }

    return response


@router.get("/sets/by-name", response_model=ChoiceSetResponse)
async def get_choice_set_by_name(
    db_manager: DbManager,
    name: str,
):
    """
    Return the data of a specific choice set by its name

    Parameters
    ----------
        name - name of the choice set

    Returns
    -------
        dict with set_id, set_name, language_code and labels keys
    """

    # load choice set by name
    stmt = select(Choice).where(and_(Choice.set_name == name))

    _session: AsyncSession
    async with db_manager.get_session() as _session:
        result = await _session.execute(stmt)
        records = result.scalars().all()

        if not records:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"name": ErrorMessage.ATTRIBUTE_NOT_FOUND_MESSAGE},
            )

        # Group labels by set_name

        grouped_labels = []
        for record in records:
            grouped_labels.append(record.value)

        # Prepare response
        response = {
            "set_id": records[0].set_id,
            "set_name": records[0].set_name,
            "language_code": records[0].language_code,
            "labels": grouped_labels,
        }

    return response


@router.get("/{cid}", response_model=ChoiceGet)
async def get_choice(
    cid: int,
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
    Return the details of a choice

    Parameters
    ----------
        cid - choice record identifier
    Returns
    -------
        choice data
    """

    # load choice
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        db_choice = await _session.get(Choice, cid)
    if db_choice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"choice_id": "Choice not found"},
        )

    return db_choice


@router.patch("/{cid}", response_model=ChoiceGet)
async def update_choice(
    cid: int,
    choice: ChoiceUpdate,
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
    Update an existing choice

    Parameters
    ----------
        cid - identifier of the choice record we want to update
        choice - choice input data
    Returns
    -------
        the updated choice
    """
    # load choice
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        db_choice = await _session.get(Choice, cid)
    if db_choice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"choice_id": "Choice not found"},
        )

    # update attributes sent by the client
    choice_data = choice.model_dump(exclude_unset=True)
    for key, value in choice_data.items():
        setattr(db_choice, key, value)
    # save updated choice
    async with db_manager.get_session() as _session:
        _session.add(db_choice)
        await _session.commit()
        # await _session.refresh(db_choice)
    return db_choice
