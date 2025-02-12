"""Submissions router."""

from time import perf_counter

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import column, delete, func, select, table
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import (
    AggregatedObjectView,
    AuthRole,
    Organization,
    Permission,
    Restatement,
    SubmissionObj,
    TableDef,
    TableView,
    User,
)
from app.dependencies import (
    Cache,
    DbManager,
    RoleAuthorization,
    StaticCache,
    get_current_user_or_none,
)
from app.schemas.submission import (
    AggregatedValidationResponse,
    LatestReportingYearResponse,
    SubmissionCreate,
    SubmissionDelete,
    SubmissionGet,
    SubmissionList,
    SubmissionUpdate,
)
from app.service.access_manager import AccessManager, AccessType
from app.service.core.errors import SubmissionError
from app.service.core.loaders import SubmissionLoader
from app.service.core.managers import SubmissionManager
from app.service.core.utils import strip_none
from app.service.core.validator import AggregatedObjectViewValidator
from app.service.organization_service import OrganizationService
from app.service.validator_service import ValidatorService

from ..forms.form_meta import FormMeta
from ..loggers import get_nzdpu_logger
from ..utils import reflect_form_table
from .utils import (
    ErrorMessage,
    check_access_rights,
    update_user_data_last_accessed,
)

logger = get_nzdpu_logger()


# pylint: disable = too-many-arguments, not-callable, too-many-branches


# creates the router
router = APIRouter(
    prefix="/submissions",
    tags=["submissions"],
    responses={404: {"description": "Not found"}},
)


# pylint: disable = unsupported-binary-operation, too-many-locals
@router.get(
    "/validate-aggregated-submissions",
    response_model=AggregatedValidationResponse,
)
async def validate_aggregated(
    cache: Cache,
    static_cache: StaticCache,
    db_manager: DbManager,
    offset: int = 0,
    limit: int = 10,
    _: User = Depends(
        RoleAuthorization(
            [
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ]
        )
    ),
):
    async with db_manager.get_session() as _session:
        validator = AggregatedObjectViewValidator(
            session=_session, static_cache=static_cache, redis_cache=cache
        )
        return await validator.validate_all(offset=offset, limit=limit)


@router.get("", response_model=SubmissionList)
async def list_submissions(
    cache: Cache,
    static_cache: StaticCache,
    db_manager: DbManager,
    start: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user_or_none),
):
    """
    Return the list of all submissions.

    Returns
    -------
        dict with start, end, total and items keys
    """
    s = perf_counter()
    async with db_manager.get_session() as _session:
        if current_user:
            # Update user.data_last_accessed for keeping track of inactivity
            await update_user_data_last_accessed(
                session=_session, current_user=current_user
            )

    async with db_manager.get_session() as _session:
        # init data structure
        submission_loader = SubmissionLoader(_session, static_cache, cache)
        submissions: list[SubmissionGet] = []
        # submissions values must be gathered from different
        #  forms and sub-forms
        async for submission in await _session.stream_scalars(
            select(SubmissionObj).offset(start).limit(limit)
        ):
            # so for each submission we found, we query its forms
            #  and sub-forms
            submissions.append(
                await submission_loader.load(submission.id, use_aggregate=True)
            )

        # Get total number of records
        total_stmt = select(func.count()).select_from(SubmissionObj)
        total_result = await _session.execute(total_stmt)
        total = total_result.scalar_one()
    for submission in submissions:
        submission.values = strip_none(submission.values)

    response = {
        "start": start,
        "end": start + len(submissions),
        "total": total,
        "items": submissions,
    }

    logger.debug(f"Execution time: {perf_counter() - s}")
    return response


@router.get(
    "/{lei}/{reported_year:int}",
    response_model=SubmissionGet,
)
async def get_submission_by_lei(
    lei: str,
    reported_year: int,
    db_manager: DbManager,
    static_cache: StaticCache,
    cache: Cache,
    current_user: User = Depends(
        RoleAuthorization(
            [
                "__NOT_A_USER__",
                AuthRole.DATA_EXPLORER,
                AuthRole.DATA_PUBLISHER,
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ]
        )
    ),
):
    s = perf_counter()

    logger.debug(f"Time elapsed before submission load: {perf_counter() - s}")
    sl = perf_counter()
    async with db_manager.get_session() as _session:
        submission_loader = SubmissionLoader(_session, static_cache, cache)
        submission = await submission_loader.load_by_lei_and_year(
            lei=lei, reported_year=reported_year, use_aggregate=True
        )
        logger.debug(f"Submission loaded in : {perf_counter() - sl}")
        logger.debug(f"Exiting session: {perf_counter() - sl}")
    submission.values = strip_none(submission.values)
    submission_data = {
        "id": submission.id,
        "nz_id": submission.nz_id,
        "name": submission.name,
        "lei": submission.lei,
        "user_id": submission.user_id,
        "submitted_by": submission.submitted_by,
        "table_view_id": submission.table_view_id,
        "permissions_set_id": submission.permissions_set_id,
        "revision": submission.revision,
        "data_source": submission.data_source,
        "status": submission.status,
        "values": submission.values,
    }
    submission = SubmissionGet(**submission_data)
    logger.debug(f"Execution time: {perf_counter() - s}")
    return submission


@router.get("/{submission_id}", response_model=SubmissionGet)
async def get_submission(
    submission_id: int,
    static_cache: StaticCache,
    cache: Cache,
    db_manager: DbManager,
    current_user: User = Depends(
        RoleAuthorization(
            [
                "__NOT_A_USER__",
                AuthRole.DATA_EXPLORER,
                AuthRole.DATA_PUBLISHER,
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ]
        )
    ),
):
    """
    Return the details of a submission

    Parameters
    ----------
        submission_id - submission identifier

    Returns
    -------
        submission data
    """
    s = perf_counter()
    if current_user:
        async with db_manager.get_session() as _session:
            # Update user.data_last_accessed for keeping track of inactivity
            await update_user_data_last_accessed(
                session=_session, current_user=current_user
            )

    logger.debug(f"Time elapsed before submission load: {perf_counter() - s}")
    sl = perf_counter()
    async with db_manager.get_session() as _session:
        submission_loader = SubmissionLoader(_session, static_cache, cache)
        submission = await submission_loader.load(
            submission_id, use_aggregate=True
        )
        logger.debug(f"Submission loaded in : {perf_counter() - sl}")
        logger.debug(f"Exiting session: {perf_counter() - sl}")
    submission.values = strip_none(submission.values)
    submission_data = {
        "id": submission.id,
        "nz_id": submission.nz_id,
        "name": submission.name,
        "lei": submission.lei,
        "user_id": submission.user_id,
        "submitted_by": submission.submitted_by,
        "table_view_id": submission.table_view_id,
        "permissions_set_id": submission.permissions_set_id,
        "revision": submission.revision,
        "data_source": submission.data_source,
        "status": submission.status,
        "values": submission.values,
    }
    submission = SubmissionGet(**submission_data)
    logger.debug(f"Execution time: {perf_counter() - s}")
    return submission


@router.delete(
    "/{submission_name}",
    response_model=SubmissionDelete,
)
async def delete_submission(
    cache: Cache,
    db_manager: DbManager,
    submission_name: str,
    _=Depends(
        RoleAuthorization(
            [
                AuthRole.ADMIN,
                AuthRole.SCHEMA_EDITOR,
                AuthRole.DATA_PUBLISHER,
            ]
        )
    ),
):
    """
    Delete a submission and all related records
    Parameters
    ----------
    session - database session
    submission_name - name of the submission

    Returns
    -------
    deletion response
    status of delete
    how many record deleted
    """
    # Fetch the SubmissionObj for the specified submission and revision
    stmt = select(SubmissionObj).where(SubmissionObj.name == submission_name)
    deleted_revisions = 0
    async with db_manager.get_session() as _session:
        submission_objs = await _session.scalars(stmt)

        if not submission_objs:
            raise HTTPException(
                status_code=404,
                detail={
                    "submission_name": (
                        SubmissionError.SUBMISSION_NOT_FOUND_MESSAGE
                    )
                },
            )

        # Get the associated forms for the submission

        query = select(TableDef.name)
        # Execute the query and fetch all names
        names = await _session.execute(query)
        all_names = [
            row[0] + "_heritable" if row[0] != "nzdpu_form" else row[0]
            for row in names.all()
        ]
        try:
            # Delete records from the associated form tables for each submission_obj
            for submission_obj in submission_objs:
                obj_id = submission_obj.id
                for form_name in all_names:
                    form_table = table(form_name)
                    delete_stmt = delete(form_table).where(
                        column(FormMeta.f_obj_id) == obj_id
                    )
                    await _session.execute(delete_stmt)
                # Delete the SubmissionObj
                await _session.execute(
                    delete(Restatement).where(Restatement.obj_id == obj_id)
                )
                await _session.delete(submission_obj)
                deleted_revisions += (
                    1  # Increment the counter for each deleted revision
                )
                await cache.del_pattern(
                    cache.wis_keys.submission + str(obj_id)
                )
            await _session.commit()

        except Exception as e:
            await _session.rollback()
            raise HTTPException(
                status_code=500,
                detail={"error": f"Failed to delete the revision {e}"},
            ) from e
    response = {"success": True, "deleted_revisions": deleted_revisions}
    return response


@router.delete("", response_model=SubmissionDelete)
async def delete_all_submission(
    cache: Cache,
    background_tasks: BackgroundTasks,
    db_manager: DbManager,
    _=Depends(RoleAuthorization([AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR])),
):
    """
    Delete all submission and all related records
    Parameters
    ----------
    session - database session
    submission_name - name of the submission

    Returns
    -------
    deletion response
    status of delete
    how many record deleted
    """
    # first of all add task to invalidate all cache
    background_tasks.add_task(cache.flushdb, asynchronous=True)
    # Fetch the SubmissionObj for the specified submission and revision
    stmt = select(SubmissionObj)
    deleted_revisions = 0
    async with db_manager.get_session() as _session:
        submission_objs = await _session.execute(stmt)
        submission_objs = submission_objs.fetchall()

        if not submission_objs:
            raise HTTPException(
                status_code=404,
                detail={
                    "no submission": (
                        SubmissionError.SUBMISSION_NOT_FOUND_MESSAGE
                    )
                },
            )

        # Get the associated forms for the submission

        query = select(TableDef.name)
        # Execute the query and fetch all names
        names = await _session.execute(query)
        all_names = [
            row[0] + "_heritable" if row[0] != "nzdpu_form" else row[0]
            for row in names.all()
        ]
        all_names.append("wis_restatement")

        try:
            # Delete records from the associated form tables for each submission_obj
            for submission_obj in submission_objs:
                for form_name in all_names:
                    # Use the form name to construct the DELETE statement
                    form = await reflect_form_table(_session, form_name)

                    query = delete(form).where(
                        form.c.obj_id == submission_obj[0].id
                    )

                    await _session.execute(query)
                # Delete the SubmissionObj
                await _session.delete(submission_obj[0])
                deleted_revisions += (
                    1  # Increment the counter for each deleted revision
                )
            await _session.commit()

        except Exception as e:
            await _session.rollback()
            raise HTTPException(
                status_code=500,
                detail={"error": f"Failed to delete the revision {e}"},
            ) from e
    response = {"success": True, "deleted_revisions": deleted_revisions}
    return response


# pylint: disable = too-many-locals
@router.post("", response_model=SubmissionGet)
async def create_submission(
    submission: SubmissionCreate,
    static_cache: StaticCache,
    cache: Cache,
    db_manager: DbManager,
    current_user: User = Depends(
        RoleAuthorization(
            [AuthRole.DATA_PUBLISHER, AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR]
        )
    ),
):
    """
    Creates a new submission

    Parameters
    ----------
        submission - submission input data

    Returns
    -------
        the new submission
    """
    s = perf_counter()
    try:
        async with db_manager.get_session() as _session:
            # Update user.data_last_accessed for keeping track of inactivity
            await update_user_data_last_accessed(
                session=_session, current_user=current_user
            )
            # check permission exists
            if submission.permissions_set_id is not None:
                permission = await _session.scalar(
                    select(Permission).where(
                        Permission.set_id == submission.permissions_set_id
                    )
                )
                if not permission:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail={
                            "submission.permissions_set_id": (
                                "Invalid permission_set_id, select existent"
                                " permission_set_id"
                            )
                        },
                    )
            try:
                table_views = await static_cache.table_views()
                table_view: TableView = table_views[submission.table_view_id]
            except KeyError:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "table_view_id": (
                            ErrorMessage.TABLE_VIEW_NOT_FOUND_MESSAGE
                        )
                    },
                )
            if not table_view.active:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "submission.table_view_id": (
                            ErrorMessage.TABLE_VIEW_NOT_ACTIVE_MESSAGE
                        )
                    },
                )

            # check has write access
            await check_access_rights(
                session=_session,
                entity=submission,
                user=current_user,
                access_type=AccessType.WRITE,
                error_message={
                    "global": SubmissionError.SUBMISSION_CANT_WRITE
                },
            )

            # get lei from organization tied to user if user is not admin
            # or if lei not in submission payload
            # NOTE: this condition will need to be rethought if access roles
            # change for this function
            if not (
                AccessManager.is_admin(current_user)
                and "legal_entity_identifier" in submission.values
            ):
                organization_nz_id = await _session.scalar(
                    select(Organization.nz_id).where(
                        Organization.id == current_user.organization_id
                    )
                )
                if not organization_nz_id:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail={"lei": "No nz_id for the associated user!"},
                    )
                if not submission.nz_id:
                    submission.nz_id = organization_nz_id

            submission_manager = SubmissionManager(
                _session, static_cache, cache
            )

            organization_service = OrganizationService(db_manager)
            if submission.nz_id is None:
                organization = (
                    await organization_service.get_organization_by_lei(
                        submission.values.get("legal_entity_identifier")
                    )
                )
                if not organization:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "legal_entity_identifier": "Organization does not exist for this legal entity identifier."
                        },
                    )
                submission.nz_id = organization.nz_id

            submission_loader = SubmissionLoader(_session, static_cache, cache)

            # check duplicate submission
            await submission_manager.check_duplicate_submission(
                submission, submission.nz_id
            )

            table_views = await static_cache.table_views()
            table_view = table_views[submission.table_view_id]
            table_def = table_view.table_def

            validator_service = ValidatorService(static_cache=static_cache)
            invalid_attributes = (
                await validator_service.validate_submission_values(
                    submission.values
                )
            )
            # verify if the submission has correct attributes
            if len(invalid_attributes) > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": (
                            f"The following attributes are not valid attributes from schema: {', '.join(invalid_attributes)}"
                        )
                    },
                )

            submission_obj = await submission_manager.create(
                submission=submission,
                current_user_id=current_user.id,
                table_def=table_def,
            )

            # delete cache for this submission
            await cache.del_pattern(
                cache.wis_keys.submission + str(submission_obj.id)
            )

            submission_loaded = await submission_loader.load(
                submission_obj.id, db_only=True
            )

            await submission_manager.save_aggregate(
                submission_obj.id,
                submission_loaded.model_dump(mode="json"),
                commit=True,
            )

            submission_loaded.values = strip_none(submission_loaded.values)

            logger.debug(
                f"Time after update null values: {perf_counter() - s}"
            )

            logger.debug(f"Total time: {perf_counter() - s}")
            return submission_loaded

    except SQLAlchemyError as e:
        error_message = str(e)
        start_idx = error_message.find("<class '")
        end_idx = error_message.find("SQL:")
        if start_idx != -1 and end_idx != -1:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": (
                        "Database error occurred"
                        f" {error_message[start_idx:end_idx].strip()}"
                    )
                },
            ) from e
        if start_idx == -1 and end_idx != -1:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": (
                        "Database error occurred"
                        f" {error_message[:end_idx].strip()}"
                    )
                },
            ) from e
        raise HTTPException(
            status_code=422,
            detail={"error": f"Database error occurred {error_message}"},
        ) from e


@router.patch("/{submission_id}", response_model=SubmissionGet)
async def update_submission(
    submission_id: int,
    submission: SubmissionUpdate,
    cache: Cache,
    static_cache: StaticCache,
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization(
            [AuthRole.DATA_PUBLISHER, AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR]
        )
    ),
):
    """
    Updates an existing submission. Used only when entering submissions
    data on an empty submission.

    Parameters
    ----------
        submission_id - identifier of the submission view we want to update
        submission - submission input data

    Returns
    -------
        the updated submission
    """

    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )
    async with db_manager.get_session() as _session:
        submission_obj = await _session.get(SubmissionObj, submission_id)
        if not submission_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SubmissionError.SUBMISSION_NOT_FOUND_MESSAGE,
            )
        await check_access_rights(
            session=_session,
            entity=submission_obj,
            user=current_user,
            access_type=AccessType.WRITE,
            error_message={"global": SubmissionError.SUBMISSION_CANT_WRITE},
        )
        submission_loader = SubmissionLoader(_session, static_cache, cache)
        submission_manager = SubmissionManager(_session, static_cache, cache)
        submission_db = await submission_loader.load(
            submission_id, db_only=True
        )
        submission_obj = await submission_manager.update(
            submission_db, submission
        )
        aggregate = (
            await _session.scalars(
                select(
                    AggregatedObjectView,
                ).where(AggregatedObjectView.obj_id == submission_id)
            )
        ).first()
        submission_obj.values = strip_none(aggregate.data.get("values"))

    return submission_obj


@router.get(
    "/latest-reporting-year/",
    response_model=LatestReportingYearResponse,
)
async def get_latest_reporting_year(
    db_manager: DbManager,
    current_user: User = Depends(
        RoleAuthorization(
            [
                "__NOT_A_USER__",
                AuthRole.DATA_EXPLORER,
                AuthRole.DATA_PUBLISHER,
                AuthRole.SCHEMA_EDITOR,
                AuthRole.ADMIN,
            ]
        )
    ),
):
    """
    API to get the latest reporting year of submissions

    Returns:
        Latest reporting year
    """
    async with db_manager.get_session() as _session:
        nzdpu_form = await reflect_form_table(_session)
        stmt = (
            select(nzdpu_form.c.reporting_year)
            .join(SubmissionObj, SubmissionObj.id == nzdpu_form.c.obj_id)
            .where(SubmissionObj.active == True)
            .order_by(nzdpu_form.c.reporting_year.desc())
        )
        result = await _session.execute(stmt)
        reporting_year = result.scalar()
        if current_user:
            # Update user.data_last_accessed for keeping track of inactivity
            await update_user_data_last_accessed(
                session=_session, current_user=current_user
            )

        return LatestReportingYearResponse(year=reporting_year)
