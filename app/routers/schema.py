"""Schema router"""

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette import status

from app.db.models import AuthRole, ColumnDef, ColumnView, TableDef, TableView
from app.dependencies import Cache, DbManager, RoleAuthorization
from app.schemas.get_form import GetForm
from app.schemas.table_def import (
    GetSchemaID,
    SchemaUpdatePayload,
    SchemaUpdateResponse,
    TableDefGet,
)

from .utils import ErrorMessage, update_user_data_last_accessed
from ..routers.utils import create_cache_key

# pylint: disable = cyclic-import, singleton-comparison

# authentication scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# creates the router
router = APIRouter(
    prefix="/schema",
    tags=["schema"],
    responses={404: {"description": "Not found"}},
)


@router.get("", response_model=list[TableDefGet])
async def list_schemas(
    db_manager: DbManager,
    filter_by: str | None = None,
    order_by: str | None = None,
    order: str = "asc",
    _=Depends(
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
    Return the list of root table definitions corresponding to configured schemas

    Parameters
    ----------
        filter_by - filter as dict e.g. {"name":"sample", "active":"true"}
        order_by - list of ordering fields e.g. ["name","id"]
        order - default "asc", can apply "asc" and "desc"

    Returns
    -------
        list of tables definition
    """
    # load table definitions
    async with db_manager.get_session() as _session:
        # verify order parameter
        if order not in ["asc", "desc"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid order value {order}. Must be 'asc' or 'desc'."
                ),
            )

        # parse the filter_by and order_by parameters
        filter_dict = {}
        order_by_list = []
        if filter_by:
            try:
                filter_dict = json.loads(filter_by)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Invalid filter format. Must be a valid JSON string."
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

        # load table def
        query = select(TableDef).where(TableDef.heritable == False)

        # apply filtering from filter_by query params
        if "name" in filter_dict:
            query = query.where(
                TableDef.name.ilike(f"%{filter_dict['name']}%")
            )
        if "active" in filter_dict and filter_dict["active"].lower() == "true":
            pass
        elif (
            "active" in filter_dict
            and filter_dict["active"].lower() == "false"
        ):
            pass

        # order by query parameter
        for field in order_by_list:
            if field == "id":
                query = query.order_by(
                    TableDef.id.asc() if order == "asc" else TableDef.id.desc()
                )
            elif field == "name":
                query = query.order_by(
                    TableDef.name.asc()
                    if order == "asc"
                    else TableDef.name.desc()
                )
            elif field == "active":
                pass
            elif field == "created_on":
                query = query.order_by(
                    TableDef.created_on.asc()
                    if order == "asc"
                    else TableDef.created_on.desc()
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Invalid order_by value {field}."
                        " Must be id, name, active or created_on."
                    ),
                )

        result = await _session.execute(query)

    return result.scalars().all()


@router.get("/get-id", response_model=GetSchemaID)
async def get_schema_id_by_name(
    name: str,
    db_manager: DbManager,
    _=Depends(
        RoleAuthorization(
            visible_roles=[
                AuthRole.DATA_PUBLISHER,
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ]
        )
    ),
):
    """
    Return the identifier of a schema (table definition) given its name

    Parameters
    ----------
        name - name of the schema we want the identifier of
    Returns
    -------
        schema identifier
    """
    # load schema
    async with db_manager.get_session() as _session:
        result = await _session.execute(
            select(TableDef).where(TableDef.name == name)
        )
        schema = result.scalars().first()

    if not schema:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"name": f"cannot find schema '{name}'"},
        )

    return {"id": schema.id}


@router.get("/full", response_model=GetForm)
async def get_schema(
    table_id: int,
    background_tasks: BackgroundTasks,
    cache: Cache,
    request: Request,
    db_manager: DbManager,
    _=Depends(
        RoleAuthorization(
            visible_roles=[
                AuthRole.DATA_PUBLISHER,
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ]
        )
    ),
):
    """
    Return a full schema definition

    Parameters
    ----------
        table_id - identifier of the root table definition for the schema
        session - database session
    Returns
    -------
        full schema definition
    """

    # try loading from cache first

    from app.forms.form_reader import FormReader

    # Define a key for caching in Redis
    redis_key = create_cache_key(request)

    # Check if the data is already in Redis cache
    cached_data = await cache.get(redis_key)

    if cached_data is not None:
        # Data is found in Redis cache, parse it and return
        schema = GetForm(**json.loads(cached_data))
    else:
        # Data is not in Redis cache, query the database
        reader = FormReader(root_id=table_id)
        async with db_manager.get_session() as _session:
            schema = await reader.read(_session)

        if not schema:
            raise HTTPException(
                status_code=404, detail={"table_id": "Table not found"}
            )

        # Serialize the schema to JSON and store it in Redis for future requests
        background_tasks.add_task(
            cache.set, redis_key, json.dumps(jsonable_encoder(schema))
        )

    return schema


@router.post("/{table_id}", response_model=SchemaUpdateResponse)
async def update_schema(
    db_manager: DbManager,
    table_id: int,
    payload: SchemaUpdatePayload,
    current_user=Depends(
        RoleAuthorization(
            [
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ]
        )
    ),
) -> SchemaUpdateResponse:
    """
    Updates a schema by adding new attributes or modifying existing
    attributes. Requires role "Form Admin".

    Parameters
    ----------
        table_id - identifier of the root table in the schema.
        add_attributes (optional) - list of attribute definitions for
            new attributes.
        update_attributes (optional) - list of attribute definitions for
            attributes that we want to update.

    Returns
    -------
        added (int) - the quantity of added attributes.
        updated (int) - the quantity of updated attributes.
    """

    _session: AsyncSession
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        table_def = await _session.scalar(
            select(TableDef)
            .where(TableDef.id == table_id)
            .options(selectinload(TableDef.columns))
            .options(
                selectinload(  # query for active table view only
                    TableDef.views.and_(  # use in case of attribute creation
                        TableView.active == True
                    )
                ).selectinload(TableView.column_views)
            )
        )
        if table_def is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"table_id": ErrorMessage.TABLE_DEF_NOT_FOUND_MESSAGE},
            )

        # attributes to update
        updated: int = 0
        for attribute in payload.update_attributes:
            column_def = await _session.scalar(
                select(ColumnDef).where(ColumnDef.id == attribute.id)
            )
            # check if it exists
            if column_def is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "update_attributes": (
                            ErrorMessage.ATTRIBUTE_NOT_FOUND_MESSAGE
                        )
                    },
                )
            # check if it's associated to the table
            if column_def.table_def_id != table_id:  # type: ignore
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "update_attributes": (
                            ErrorMessage.ATTRIBUTE_NOT_IN_TABLE_DEF_MESSAGE
                        )
                    },
                )
            # update it
            await column_def.update(
                session=_session,
                name=attribute.name,
                table_def_id=None,  # keep the same
                user_id=attribute.user_id,
                attribute_type_id=attribute.attribute_type_id,
                choice_set_id=attribute.choice_set_id,
            )

            updated += 1

        # attributes to add
        added: int = 0
        for attribute in payload.add_attributes:
            # skip if already in the schema
            if attribute.name in [col.name for col in table_def.columns]:
                continue
            # check attribute already exists in the DB
            db_attribute = await _session.scalar(
                select(ColumnDef).where(ColumnDef.name == attribute.name)  # type: ignore
            )
            if db_attribute is None:
                # create attribute
                attribute = ColumnDef(
                    table_def_id=table_id,
                    name=attribute.name,
                    user_id=attribute.user_id,
                    attribute_type=attribute.attribute_type,
                    attribute_type_id=attribute.attribute_type_id,
                    choice_set_id=attribute.choice_set_id,
                )
                _session.add(attribute)
                await _session.flush()
                db_attribute = attribute
                # create corresponding default column view
                try:
                    # there should be only one available active view
                    table_view = table_def.views[0]
                except IndexError as exc:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "add_attributes": (
                                ErrorMessage.NO_ASSOCIATED_TABLE_VIEW_MESSAGE
                            )
                        },
                    ) from exc
                attribute_view = ColumnView(
                    column_def_id=attribute.id,
                    table_view_id=table_view.id,
                )
                _session.add(attribute_view)
                await _session.flush()
                # add the column view to the associated table view
                table_view.column_views.append(attribute_view)

            # add attribute to table
            table_def.columns.append(db_attribute)
            added += 1

        await _session.commit()

    return SchemaUpdateResponse(
        added=added,
        updated=updated,
    )
