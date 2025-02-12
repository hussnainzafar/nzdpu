"""Table view router"""

import json
from enum import Enum

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette import status

from app.db.models import AuthRole, ColumnDef, ColumnView, TableView
from app.dependencies import Cache, DbManager, RoleAuthorization, oauth2_scheme
from app.forms.attribute_reader.attribute_reader import ReaderContext
from app.forms.form_reader import FormReader
from app.routers.utils import (
    ErrorMessage,
    check_access_rights,
    create_cache_key,
    load_table_def,
    load_table_view,
    update_user_data_last_accessed,
)
from app.schemas import table_view as table_view_schema
from app.schemas.column_def import AttributeType
from app.schemas.create_form import ViewRevisionCreate
from app.schemas.table_view import (
    AttributeViewGetFull,
    TableViewGetFull,
    TableViewRevisionUpdatePayload,
    TableViewRevisionUpdateResponse,
)
from app.service.access_manager import AccessManager, AccessType

from .utils import check_admin_access_rights

# pylint: disable = singleton-comparison

# creates the router
router = APIRouter(
    prefix="/schema/views",
    tags=["views"],
    dependencies=[Depends(oauth2_scheme)],
    responses={404: {"description": "Not found"}},
)


class ViewError(str, Enum):
    """
    Table view errors
    """

    TABLE_DEF_NOT_FOUND_MESSAGE = "Table definition not found."
    TABLE_VIEW_NOT_FOUND_MESSAGE = "Table view not found."
    TABLE_VIEW_CANT_READ = "User not allowed to read this view."
    TABLE_VIEW_CANT_WRITE = "User not allowed to write this view."
    TABLE_VIEW_REVISION_CANT_WRITE = "User not allowed to write view revision."
    TABLE_VIEW_NO_ACTIVE_REVISION = "No active view revision found."


@router.get("", response_model=list[table_view_schema.TableViewGet])
async def list_views(
    db_manager: DbManager,
    filter_by: str | None = None,
    order_by: str | None = None,
    order: str = "asc",
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
    Return the list of views for a given table.

    Parameters
    ----------
        filter_by - filter as dict e.g. {"name":"sample", "revision":"1"}
        order_by - list of ordering fields e.g. ["name","id"]
        order - default "asc", can apply "asc" and "desc"
    Returns
    -------
        the list of views
    """
    # load views
    async with db_manager.get_session() as _session:
        # access manager
        access_manager = AccessManager(_session)
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

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

        # load table views
        query = select(TableView)
        result = await _session.execute(query)

        # check list access rights
        is_admin, views_ids_list = await access_manager.can_list(
            entities=result.scalars().all(), user=current_user
        )

        # check if it is not admin -> query granted ids
        if not is_admin:
            query = query.where(TableView.id.in_(views_ids_list))

        # apply filtering from filter_by query params
        if "name" in filter_dict:
            query = query.where(
                TableView.name.ilike(f"%{filter_dict['name']}%")
            )
        if "revision" in filter_dict:
            revision = int(filter_dict["revision"])
            query = query.where(TableView.revision == revision)

        # order by query parameter
        for field in order_by_list:
            if field == "id":
                query = query.order_by(
                    TableView.id.asc()
                    if order == "asc"
                    else TableView.id.desc()
                )
            elif field == "name":
                query = query.order_by(
                    TableView.name.asc()
                    if order == "asc"
                    else TableView.name.desc()
                )
            elif field == "revision":
                query = query.order_by(
                    TableView.revision.asc()
                    if order == "asc"
                    else TableView.revision.desc()
                )
            elif field == "created_on":
                query = query.order_by(
                    TableView.created_on.asc()
                    if order == "asc"
                    else TableView.created_on.desc()
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


@router.get("/{table_view_id}", response_model=table_view_schema.TableViewGet)
async def get_view(
    table_view_id: int,
    db_manager: DbManager,
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
    Return the details of a table view

    Parameters
    ----------
        table_view_id - table view identifier
    Returns
    -------
        table view data
    """
    # load table view
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        table_view = await load_table_view(table_view_id, _session)

        # check read access rights
        await check_access_rights(
            session=_session,
            entity=table_view,
            user=current_user,
            access_type=AccessType.READ,
            error_message={"global": ViewError.TABLE_VIEW_CANT_READ},
        )

    return table_view


@router.post("", response_model=table_view_schema.TableViewGet)
async def create_view(
    table_view: table_view_schema.TableViewCreate,
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
    Creates a new table view

    Parameters
    ----------
        table_view - table view input data
    Returns
    -------
        the new table view
    """
    # check provided table def exists
    table_def_id = table_view.table_def_id
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # check admin access rights
        await check_admin_access_rights(
            session=_session, current_user=current_user
        )

        await load_table_def(table_def_id, _session)

        # Check if user_id is specified in the request body
        if "user_id" not in table_view.model_dump() or table_view.user_id in [
            None,
            0,
        ]:
            table_view.user_id = (
                current_user.id
            )  # Set user_id to the ID of the currently logged-in user

        db_table_view = TableView(**table_view.model_dump())

        # check write access rights
        await check_access_rights(
            session=_session,
            entity=db_table_view,
            user=current_user,
            access_type=AccessType.WRITE,
            error_message={"global": ViewError.TABLE_VIEW_CANT_WRITE},
        )
        _session.add(db_table_view)
        await _session.commit()
    return db_table_view


@router.patch("/revisions", response_model=TableViewRevisionUpdateResponse)
async def update_view_revision(
    name: str,
    revision: int,
    payload: TableViewRevisionUpdatePayload,
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
    Updates a revision of a table view.

    Parameters
    ----------
        name (str) - name of the table view we want to update.
        revsion (int): revision of the table view we want to update.
        payload (TableViewRevisionUpdatePayload): update revision payload.
            It supports field `add_attributes` and `remove_attributes`
            which hold a list of attributes IDs to add/remove, and a
            boolean field `active` to set the revision as active,
            disabling all other revisions of the same view.
    Returns
    -------
        the operation results, which include the number of attributes
        that were added or removed
    """
    _session: AsyncSession
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # check admin access rights
        await check_admin_access_rights(
            session=_session, current_user=current_user
        )
        # load table view and all of its revisions
        table_views = await _session.stream_scalars(
            select(TableView)
            .where(TableView.name == name)
            .order_by(TableView.revision.desc())
            .options(selectinload(TableView.column_views))
        )
        table_view = None
        # get the latest revision
        other_revisions = []
        async for table_view_revision in table_views:
            if table_view_revision.revision == revision:
                table_view = table_view_revision
            else:
                other_revisions.append(table_view_revision)
        # table_view = table_views[0]
        # check if table view exists
        if table_view is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "name": ErrorMessage.TABLE_VIEW_REVISION_NOT_FOUND_MESSAGE
                },
            )
        # load attributes to add
        attributes_to_add = await _session.stream_scalars(
            select(ColumnView).where(
                ColumnView.id.in_(
                    payload.add_attributes if payload.add_attributes else []
                )
            )
        )
        # add attributes to view
        added = 0
        async for attribute in attributes_to_add:
            # if it's here it exists, so we can remove it from the check
            payload.add_attributes.remove(attribute.id)  # type: ignore
            # here we remove from the initial list to check if any ids
            # remain, in that case they were not included as results in
            # the select, thus they do not exist in the database
            if attribute not in table_view.column_views:
                table_view.column_views.append(attribute)
                added += 1
        # check all attributes exist
        if payload.add_attributes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "add_attributes": (
                        "The following attribute view IDs do not exist:"
                        f" {payload.add_attributes}"
                    )
                },
            )
        # remove attributes from view
        attributes_to_remove = await _session.stream_scalars(
            select(ColumnView).where(
                ColumnView.id.in_(
                    payload.remove_attributes
                    if payload.remove_attributes
                    else []
                )
            )
        )
        # remove attributes from view
        removed = 0
        async for attribute in attributes_to_remove:
            # if it's here it exists, so we can remove it from the check
            payload.remove_attributes.remove(attribute.id)  # type: ignore
            # here we remove from the initial list to check if any ids
            # remain, in that case they were not included as results in
            # the select, thus they do not exist in the database
            try:
                table_view.column_views.remove(attribute)
                removed += 1
            except ValueError:
                # not in the view already so not worth to raise?
                continue
        # check all attributes exist
        if payload.remove_attributes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "remove_attributes": (
                        "The following attribute view IDs do not exist:"
                        f" {payload.remove_attributes}"
                    )
                },
            )
        # set active
        table_view.active = payload.active
        # if active == True, set all other revisions as non active
        if payload.active:
            for table_view_revision in other_revisions:
                table_view_revision.active = False

        await _session.commit()

        return TableViewRevisionUpdateResponse(
            added=added,
            removed=removed,
            active=table_view.active,
        )


@router.patch(
    "/{table_view_id}", response_model=table_view_schema.TableViewGet
)
async def update_view(
    table_view_id: int,
    table_view_data: table_view_schema.TableViewUpdate,
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
    Update an existing table view

    Parameters
    ----------
        table_view_id - identifier of the table view we want to update
        table_view_data - table view input data
    Returns
    -------
        the updated table view
    """
    # load table view
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # check admin access rights
        await check_admin_access_rights(
            session=_session, current_user=current_user
        )

        db_table_view = await load_table_view(table_view_id, _session)

        # check write access rights
        await check_access_rights(
            session=_session,
            entity=db_table_view,
            user=current_user,
            access_type=AccessType.WRITE,
            error_message={"global": ViewError.TABLE_VIEW_CANT_WRITE},
        )
        # update table view sent by the client
        table_view_update = table_view_data.model_dump(exclude_unset=True)
        for key, value in table_view_update.items():
            setattr(db_table_view, key, value)
        # save updated table view
        _session.add(db_table_view)
        await _session.commit()

    return db_table_view


@router.get("/full/{name}", response_model=TableViewGetFull)
async def get_view_schema(
    name: str,
    background_tasks: BackgroundTasks,
    cache: Cache,
    request: Request,
    db_manager: DbManager,
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
    Return the full schema of a table view

    Parameters
    ----------
        name - table view name
    Returns
    -------
        full schema definition derived from this view
    """
    # Define a key for caching in Redis
    redis_key = create_cache_key(request)

    # Check if the data is already in Redis cache
    cached_data = await cache.get(redis_key)

    if cached_data:
        # Data is found in Redis cache, parse it and return
        view_schema = TableViewGetFull(**json.loads(cached_data))

    else:
        _session: AsyncSession
        async with db_manager.get_session() as _session:
            # Update user.data_last_accessed for keeping track of inactivity
            await update_user_data_last_accessed(
                session=_session, current_user=current_user
            )
        async with db_manager.get_session() as _session:
            # load active revision
            result = await _session.execute(
                select(TableView)
                .options(
                    selectinload(TableView.column_views).options(
                        selectinload(ColumnView.column_def).options(
                            selectinload(ColumnDef.prompts),
                            selectinload(ColumnDef.choices),
                        )
                    ),
                    selectinload(TableView.table_def),
                )
                .where(TableView.name == name)
                .where(TableView.active == True)
                .order_by(TableView.revision.desc())
                .limit(1)
            )
            view: TableView = result.scalars().first()
            if not view:
                # no active revision found
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"name": ViewError.TABLE_VIEW_NO_ACTIVE_REVISION},
                )
            # initialize response model
            view_schema: TableViewGetFull = TableViewGetFull.model_validate(
                view
            )
            attr_views_schema: list[AttributeViewGetFull] = []
            for attr_view in view.column_views:
                # build schema of attribute view
                attr_view_schema = AttributeViewGetFull.model_validate(
                    attr_view
                )
                if (
                    attr_view_schema.column_def.attribute_type
                    == AttributeType.FORM
                ):
                    # build sub-form
                    assert attr_view_schema.column_def.attribute_type_id > 0
                    reader = FormReader(
                        root_id=attr_view_schema.column_def.attribute_type_id,
                        context=ReaderContext.VIEW_SCHEMA,
                    )
                    attr_view_schema.column_def.form = await reader.read(
                        session=_session
                    )

                # add attribute views schema
                attr_views_schema.append(attr_view_schema)

            # include attribute views in response
            view_schema.attribute_views = attr_views_schema
        # Serialize the schema to JSON and store it in Redis for future requests
        background_tasks.add_task(
            cache.set, redis_key, json.dumps(jsonable_encoder(view_schema))
        )

    return view_schema


@router.post("/revisions", response_model=ViewRevisionCreate)
async def create_view_revision(
    name: str,
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
    Creates a new revision of an existing form view

    Parameters
    ----------
        name - name of the form view we want to create a new revision of
    Returns
    -------
        information about the new revision
    """
    from app.forms.form_builder import FormBuilder

    builder = FormBuilder()
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # check admin access rights
        await check_admin_access_rights(
            session=_session, current_user=current_user
        )

        # load current revisions
        result = await _session.execute(
            select(TableView)
            .options(selectinload(TableView.column_views))
            .where(TableView.name == name)
            .order_by(TableView.revision.desc())
        )
        current_rev = result.scalars().first()

        # check write access rights
        await check_access_rights(
            session=_session,
            entity=current_rev,
            user=current_user,
            access_type=AccessType.WRITE,
            error_message={"global": ViewError.TABLE_VIEW_REVISION_CANT_WRITE},
        )

        view_rev = await builder.create_view_revision(name, _session)
    if not view_rev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "name": f"Cannot create a new revision of form view '{name}'"
            },
        )

    # disable previous revision
    async with db_manager.get_session() as _session:
        await builder.disable_view_revision(
            name, view_rev.revision - 1, _session
        )

    return view_rev
