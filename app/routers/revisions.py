"""Revisions router."""

from datetime import datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    status,
)
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AggregatedObjectView,
    AuthRole,
    Restatement,
    SubmissionObj,
    TableDef,
    User,
)
from app.dependencies import Cache, DbManager, RoleAuthorization, StaticCache
from app.schemas.submission import (
    RevisionUpdate,
    SubmissionDeleteResponse,
    SubmissionEditModeResponse,
    SubmissionGet,
    SubmissionObjStatusEnum,
    SubmissionPublishResponse,
    SubmissionRevisionList,
    SubmissionRollback,
)
from app.service.access_manager import AccessType
from app.service.core.errors import SubmissionError
from app.service.core.loaders import FormBatchLoader, SubmissionLoader
from app.service.core.managers import RevisionManager, SubmissionManager

from .utils import (
    check_access_rights,
    update_user_data_last_accessed,
)
from ..loggers import get_nzdpu_logger
from ..schemas.restatements import RestatementGetSimple
from ..service.core.forms import FormValuesGetter
from ..service.core.utils import strip_none

logger = get_nzdpu_logger()

# pylint: disable = unsupported-binary-operation, too-many-instance-attributes

# creates the router
router = APIRouter(
    tags=["revisions"],
    responses={404: {"description": "Not found"}},
)


@router.get("/{submission_name}", response_model=SubmissionRevisionList)
async def list_revisions(
    cache: Cache,
    static_cache: StaticCache,
    db_manager: DbManager,
    submission_name: str,
    active: bool | None = None,
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
    Return the revision history for a submission.

    Parameters
    ----------
        submission_name (optional) - name of the submission we are
            requesting revisions of.
        active (optional) - filters revisions by their "active" flag. If
            not set, all revisions are returned, regardless of their
            "active" flag.

    Returns
    -------
        the list of revisions, ordered by descending revision number.
    """
    if current_user:
        async with db_manager.get_session() as _session:
            # Update user.data_last_accessed for keeping track of inactivity
            await update_user_data_last_accessed(
                session=_session, current_user=current_user
            )

    stmt = select(SubmissionObj).where(SubmissionObj.name == submission_name)
    if active is not None:
        stmt = stmt.where(SubmissionObj.active == active)
    # get submissions
    _session: AsyncSession
    async with db_manager.get_session() as _session:
        submissions = (
            await _session.scalars(
                stmt.order_by(SubmissionObj.revision.desc())
            )
        ).all()
        submission_loader = SubmissionLoader(_session, static_cache, cache)
        loaded_submissions = []
        for submission in submissions:
            loaded_submissions.append(
                await submission_loader.load(submission.id)
            )

    submissions_valued = []
    for sub in loaded_submissions:
        sub.values = strip_none(sub.values)  # type: ignore
        submissions_valued.append(sub.model_dump(mode="json"))

    subs_count = len(submissions_valued)
    return {
        "start": 0,
        "end": subs_count - 1,
        "total": subs_count,
        "items": submissions_valued,
    }


@router.get(
    "/{submission_name}/{revision_index}", response_model=SubmissionGet
)
async def get_revision(
    cache: Cache,
    db_manager: DbManager,
    static_cache: StaticCache,
    submission_name: str,
    revision_index: int,
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
    Get a revision
    Parameters
    ----------
    session - database session
    submission_name - name of the submission
    revision_index - revision index

    Returns
    -------
    revision data
    """

    stmt = (
        select(SubmissionObj)
        .where(SubmissionObj.name == submission_name)
        .where(SubmissionObj.revision == revision_index)
    )
    async with db_manager.get_session() as _session:
        if current_user:
            # Update user.data_last_accessed for keeping track of inactivity
            await update_user_data_last_accessed(
                session=_session, current_user=current_user
            )
        submission_obj: SubmissionObj = await _session.scalar(stmt)
        if not submission_obj:
            raise HTTPException(
                status_code=404,
                detail={
                    "submission_name": (
                        SubmissionError.SUBMISSION_NOT_FOUND_MESSAGE
                    )
                },
            )
        submission_loader = SubmissionLoader(_session, static_cache, cache)
        submission = await submission_loader.load(
            submission_obj.id, use_aggregate=True
        )

        submission.values = strip_none(submission.values)  # type: ignore

    return submission


@router.delete(
    "/{submission_name}/{revision_index}",
    response_model=SubmissionDeleteResponse,
)
async def delete_revision(
    cache: Cache,
    static_cache: StaticCache,
    background_tasks: BackgroundTasks,
    db_manager: DbManager,
    submission_name: str,
    revision_index: int,
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
    Delete a revision and all related records
    Parameters
    ----------
    session - database session
    submission_name - name of the submission
    revision_index - revision index

    Returns
    -------
    deletion response
    """
    # first of all add task to invalidate all cache
    background_tasks.add_task(cache.flushdb, asynchronous=True)
    # You cannot delete original submission with this API.
    if revision_index == 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "revision_index": (
                    "You cannot delete the original submission with this"
                    " API.If you want to delete the original submission you"
                    " can use the delete submission API."
                )
            },
        )

    # Fetch the SubmissionObj for the specified submission and revision
    stmt = (
        select(SubmissionObj)
        .where(SubmissionObj.name == submission_name)
        .where(SubmissionObj.revision == revision_index)
    )

    _session: AsyncSession
    async with db_manager.get_session() as _session:
        submission_obj: SubmissionObj = await _session.scalar(stmt)

        if not submission_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "submission_name": (
                        SubmissionError.SUBMISSION_NOT_FOUND_MESSAGE
                    )
                },
            )

        # If this revision was active we need to activate some other revision.
        is_deleted_revision_active = submission_obj.active

        # Get the associated forms for the submission
        query = select(TableDef.name)
        # Execute the query and fetch all names
        names = await _session.execute(query)
        all_names = [
            row[0] + "_heritable" if row[0] != "nzdpu_form" else row[0]
            for row in names.all()
        ]
        try:
            # Delete records from the associated form tables

            restatements_delete = delete(Restatement).where(
                Restatement.obj_id == submission_obj.id
            )
            await _session.execute(restatements_delete)

            for form_name in all_names:
                # Use the form name to construct the DELETE statement
                form_table = await static_cache.get_form_table(form_name)
                query = delete(form_table).where(
                    form_table.c.obj_id == submission_obj.id
                )
                await _session.execute(query)

            # Delete the SubmissionObj
            await _session.delete(submission_obj)
            await _session.commit()

        except Exception as e:
            await _session.rollback()
            raise HTTPException(
                status_code=500,
                detail={"error": f"Failed to delete the revision {e}"},
            ) from e

        if not is_deleted_revision_active:
            return {"success": True}

    async with db_manager.get_session() as _session:
        # If deleted revision was active we activate the most recent revision.
        stmt = (
            select(SubmissionObj)
            .where(SubmissionObj.name == submission_name)
            .order_by(SubmissionObj.revision.desc())
            .limit(1)
        )
        latest_submission = await _session.scalar(stmt)

        # We are preventing deletion of the original submission so there should always be a submission in our database.
        # However, if not, let us return meaningful error.
        if not latest_submission:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "revision": (
                        "Something went wrong. There is no remaining revisions"
                        " of this submission in the system."
                    )
                },
            )

        latest_submission.active = True
        await _session.flush([latest_submission])
        await _session.commit()

    return {"success": True}


@router.post("/{submission_name}", response_model=SubmissionGet)
async def create_submission_revision(
    cache: Cache,
    db_manager: DbManager,
    static_cache: StaticCache,
    submission_name: str,
    data: RevisionUpdate,
    current_user: User = Depends(
        RoleAuthorization(
            [AuthRole.DATA_PUBLISHER, AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR]
        )
    ),
) -> SubmissionGet:
    """
    Creates a new submission revision.

    Parameters
    ----------
        submission_name - the name of the submission to "update".
        data - the new values for this submission revision.

    Returns
    -------
        the new submission revision.

    """

    if not data.restatements:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"data": "No value submitted!"},
        )
    _session: AsyncSession
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        all_revisions = (
            await _session.scalars(
                select(SubmissionObj)
                .where(SubmissionObj.name == submission_name)
                .order_by(SubmissionObj.revision.desc())
            )
        ).all()

        if len(all_revisions) == 0:
            raise HTTPException(
                status_code=404,
                detail={
                    "submission_name": (
                        SubmissionError.SUBMISSION_NOT_FOUND_MESSAGE
                    )
                },
            )
        last_revision = all_revisions[0]

        # check write access rights
        await check_access_rights(
            session=_session,
            entity=last_revision,
            user=current_user,
            access_type=AccessType.WRITE,
            error_message={
                "global": SubmissionError.SUBMISSION_REVISION_CANT_WRITE
            },
        )
        if (
            last_revision.checked_out
            and last_revision.user_id != current_user.id
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"global": SubmissionError.SUBMISSION_USER_CANT_EDIT},
            )
        revision_manager = RevisionManager(
            session=_session,
            core_cache=static_cache,
            redis_cache=cache,
            rev_history=all_revisions,
        )
        try:
            updated_submission = await revision_manager.update(
                model=data,
                current_user_id=current_user.id,
                create_submission=True,
            )
        except SQLAlchemyError as e:
            detail = {
                "global": "Error while creating submission revision. Please check revision data."
            }
            logger.error(
                "Error in creating submission revision",
                detail=detail,
                data=data,
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail
            ) from e

        all_revisions = [updated_submission, *all_revisions]

        for i, sub in enumerate(all_revisions):
            last_sub = i == 0
            sub.checked_out = True if last_sub else False
            sub.checked_out_on = datetime.now() if last_sub else None
            sub.user_id = current_user.id if last_sub else None
            sub.active = True if last_sub else False

        await _session.flush(all_revisions)

        submissions_full: dict[int, SubmissionObj | SubmissionGet] = {
            sub.id: sub for sub in all_revisions
        }

        try:
            for sub in submissions_full:
                submission = SubmissionGet.model_validate(
                    submissions_full.get(sub)
                )
                await cache.del_pattern(
                    cache.wis_keys.submission + str(submission.id)
                )

                form_loader = FormBatchLoader(
                    _session, static_cache, cache, submission.id
                )
                form_data = await form_loader.fetch_form_row_data()
                primary_table_def = await form_loader.primary_form_table_def
                form_manager = FormValuesGetter(
                    static_cache,
                    cache,
                    form_rows=form_data,
                    primary_form=primary_table_def,
                )
                (
                    submission_values,
                    submission_units,
                ) = await form_manager.get_values()
                submission.values = (
                    submission_values[0] if submission_values else {}
                )
                submission.units = (
                    submission_units[0] if submission_units else {}
                )
                submissions_full[sub] = submission

            rel_aggregates = (
                await _session.execute(
                    select(
                        AggregatedObjectView.obj_id, AggregatedObjectView
                    ).where(
                        AggregatedObjectView.obj_id.in_(
                            rev.id for rev in all_revisions
                        )
                    )
                )
            ).all()

            aggregates_map = dict(
                kv for kv in (r._tuple() for r in rel_aggregates)
            )
            for sub_id, sub in submissions_full.items():
                new_data = sub.model_dump(mode="json")
                if aggregates_map.get(sub_id, False):
                    aggregates_map[sub_id].data = new_data
                else:
                    aggregates_map[sub_id] = AggregatedObjectView(
                        obj_id=sub_id,
                        data=submissions_full.get(sub_id).model_dump(
                            mode="json"
                        ),
                    )
                _session.add(aggregates_map[sub_id])

            await _session.flush(aggregates_map.values())
            await _session.commit()

            last_sub = SubmissionGet.model_validate(
                aggregates_map.get(updated_submission.id).data
            )
            last_sub.values = strip_none(last_sub.values)  # type: ignore
            return last_sub.model_dump(mode="json")

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": e},
            ) from e


@router.post(
    "/{submission_name}/edit", response_model=SubmissionEditModeResponse
)
async def set_edit_mode(
    cache: Cache,
    static_cache: StaticCache,
    db_manager: DbManager,
    submission_name: str,
    force: bool = False,
    current_user: User = Depends(
        RoleAuthorization(
            [AuthRole.DATA_PUBLISHER, AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR]
        )
    ),
) -> SubmissionEditModeResponse:
    """
    Set a submission in edit mode. If multiple revisions exist for a
    submission, the checkout is applied to the currently active one.

    Parameters
    ----------
        submission_name - the submission name.
        force - if set to True, the system overrides any existing
        checkout on this submission (default: False). Note that setting
        this parameter to True requires “Form Admin” role; otherwise,
        its value is ignored by the system.

    Returns
    -------
        the checked out submission.
    """

    _session: AsyncSession
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        stmt = (
            select(SubmissionObj)
            .where(SubmissionObj.name == submission_name)
            .order_by(SubmissionObj.revision.desc())
        )
        submission: SubmissionObj = await _session.scalar(stmt)
        loader = SubmissionLoader(_session, static_cache, cache)
        manager = SubmissionManager(_session, static_cache, cache)
        # check if already checked out
        if submission is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "submission_name": (
                        SubmissionError.SUBMISSION_NOT_FOUND_MESSAGE
                    )
                },
            )
        # invalidate cache for this submission
        redis_key = cache.wis_keys.submission + str(submission.id)
        await cache.del_pattern(redis_key)
        if submission.checked_out:
            if not force:  # revision checked out and force set to False
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "submission_name": (
                            SubmissionError.SUBMISSION_CANT_CHECK_OUT
                        )
                    },
                )
            # check if user has form admin rights
            await check_access_rights(
                session=_session,
                entity=submission,
                user=current_user,
                access_type=AccessType.READ,
                error_message={
                    "global": (
                        SubmissionError.SUBMISSION_CHECKED_OUT_BY_ANOTHER_USER
                    )
                },
            )

        submission.checked_out = True
        submission.checked_out_on = datetime.now()
        submission.user_id = current_user.id

        _session.add(submission)

        await _session.commit()

    async with db_manager.get_session() as _session:
        updated_submission = await loader.load(submission.id, db_only=True)
        try:
            await manager.save_aggregate(
                submission.id,
                updated_submission.model_dump(mode="json"),
                commit=True,
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": e},
            ) from e

    return updated_submission.model_dump(mode="json")


@router.post(
    "/{submission_name}/edit/clear", response_model=SubmissionEditModeResponse
)
async def clear_edit_mode(
    db_manager: DbManager,
    submission_name: str,
    cache: Cache,
    static_cache: StaticCache,
    current_user=Depends(
        RoleAuthorization(
            [AuthRole.DATA_PUBLISHER, AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR]
        )
    ),
) -> SubmissionEditModeResponse:
    """
    Clears the current edit mode on a submission and returns to
    normal mode.

    Parameters
    ----------
        submission_name - the submission name.

    Returns
    -------
        the cleared from check out submission.
    """

    _session: AsyncSession
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        stmt = (
            select(SubmissionObj)
            .where(SubmissionObj.name == submission_name)
            .order_by(SubmissionObj.revision.desc())
        )
        submission: SubmissionObj = await _session.scalar(stmt)
        # check if already checked out
        if submission is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "submission_name": (
                        SubmissionError.SUBMISSION_NOT_FOUND_MESSAGE
                    )
                },
            )
        if submission.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "global": (
                        SubmissionError.SUBMISSION_CANT_CLEAR_ANOTHER_USER
                    )
                },
            )
        # check if user has form admin rights
        await check_access_rights(
            session=_session,
            entity=submission,
            user=current_user,
            access_type=AccessType.READ,
            error_message={
                "global": SubmissionError.SUBMISSION_CANT_CLEAR_PERMISSION
            },
        )

        submission.checked_out = False
        submission.checked_out_on = None
        submission.user_id = None

        await _session.commit()

        async with db_manager.get_session() as _session:
            loader = SubmissionLoader(_session, static_cache, cache)
            manager = SubmissionManager(_session, static_cache, cache)
            await manager.save_aggregate(
                submission.id,
                (await loader.load(submission.id, db_only=True)).model_dump(
                    mode="json"
                ),
            )

        return submission


@router.post("/{submission_name}/rollback", response_model=SubmissionRollback)
async def rollback_submission(
    cache: Cache,
    static_cache: StaticCache,
    background_tasks: BackgroundTasks,
    db_manager: DbManager,
    submission_name: str,
    current_user=Depends(
        RoleAuthorization(
            [AuthRole.DATA_PUBLISHER, AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR]
        )
    ),
) -> SubmissionRollback:
    """
    Rollback submission to the previous revision.

    Parameters
    ----------
        submission_name - the name of the submission to "rollback".

    Returns
    -------
        rollback to the previous revision.
    """

    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        stmt = (
            select(SubmissionObj)
            .where(SubmissionObj.name == submission_name)
            .order_by(SubmissionObj.revision.desc())
        )

        all_submissions = await _session.stream_scalars(stmt)
        active_submission = None
        rollback_active_submission = None

        async for submission in all_submissions:
            # invalidate cache for this submission
            redis_key = cache.wis_keys.submission + str(submission.id)
            background_tasks.add_task(cache.del_pattern, redis_key)
            if submission.active and not active_submission:
                active_submission = submission
            elif (
                not submission.active
                and active_submission
                and not rollback_active_submission
            ):
                rollback_active_submission = submission

        if active_submission:
            active_submission.active = False
            await _session.commit()

            if rollback_active_submission:
                rollback_active_submission.active = True
                await _session.commit()
            else:
                active_submission.active = True
                await _session.commit()
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "global": (
                            SubmissionError.SUBMISSION_PREVIOUS_ACTIVE_NOT_FOUND_MESSAGE
                        )
                    },
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "global": (
                        SubmissionError.SUBMISSION_ACTIVE_NOT_FOUND_MESSAGE
                    )
                },
            )

    async with db_manager.get_session() as _session:
        loader = SubmissionLoader(_session, static_cache, cache)
        manager = SubmissionManager(_session, static_cache, cache)
        for submission in [active_submission, rollback_active_submission]:
            await manager.save_aggregate(
                submission.id,
                (await loader.load(submission.id, db_only=True)).model_dump(
                    mode="json"
                ),
            )

    response = SubmissionRollback(
        active_id=(
            rollback_active_submission.id
            if rollback_active_submission
            else None
        ),
        active_revision=(
            rollback_active_submission.revision
            if rollback_active_submission
            else None
        ),
        prev_active_id=active_submission.id if active_submission else None,
        prev_active_revision=(
            active_submission.revision if active_submission else None
        ),
        name=submission_name,
    )

    return response


@router.post("/{name}/draft", response_model=SubmissionGet)
async def save_submission_draft(
    db_manager: DbManager,
    name: str,
    submission: RevisionUpdate,
    background_tasks: BackgroundTasks,
    cache: Cache,
    static_cache: StaticCache,
    current_user: User = Depends(
        RoleAuthorization(
            [AuthRole.DATA_PUBLISHER, AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR]
        )
    ),
) -> SubmissionGet:
    """
    Saves a draft of a submission to the database
    Parameters
    ---------
        name - name of the submission we want to save
        submission - submission input data
    Returns
    -------
        the updated submission's ID, Name, Revision ID, and data
    """

    _session: AsyncSession
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )
        stmt = (
            select(SubmissionObj)
            .where(SubmissionObj.name == name)
            .order_by(SubmissionObj.revision.desc())
        )

        all_revisions = (await _session.scalars(stmt)).all()

        first_revision = all_revisions[-1]
        last_revision = all_revisions[0]

        # get submission with latest revision
        if not last_revision:
            # no submission or revision exists for the given name
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"name": f"No submission found with name {name}"},
            )
        # check access rights
        await check_access_rights(
            session=_session,
            entity=last_revision,
            user=current_user,
            access_type=AccessType.WRITE,
            error_message=SubmissionError.SUBMISSION_CANT_WRITE,
        )

        # invalidate cache for this submission
        redis_key = cache.wis_keys.submission + str(last_revision.id)
        background_tasks.add_task(cache.del_pattern, redis_key)

        revision_manager = RevisionManager(
            session=_session,
            core_cache=static_cache,
            redis_cache=cache,
            rev_history=list(all_revisions),
        )

        updated_submission = await revision_manager.update(
            model=submission,
            current_user_id=current_user.id,
            create_submission=last_revision.status
            in [None, SubmissionObjStatusEnum.PUBLISHED],
            submission_status=SubmissionObjStatusEnum.DRAFT,
        )

    async with db_manager.get_session() as _session:
        loader = SubmissionLoader(_session, static_cache, cache)
        db_submission = await loader.load(updated_submission.id, db_only=True)
        await revision_manager.save_aggregate(
            db_submission.id,
            db_submission.model_dump(mode="json"),
            commit=True,
        )

    db_submission.values = strip_none(db_submission.values)  # type: ignore

    return db_submission


@router.post("/{name}/publish", response_model=SubmissionPublishResponse)
async def publish_submission_draft(
    db_manager: DbManager,
    name: str,
    background_tasks: BackgroundTasks,
    cache: Cache,
    static_cache: StaticCache,
    request: Request,
    current_user=Depends(
        RoleAuthorization(
            [AuthRole.DATA_PUBLISHER, AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR]
        )
    ),
):
    """
    Publishes a draft of a submission to the database.

    Parameters
    ----------
    session : Session
        Database session to execute queries.
    name : str
        Name of the submission we want to save.

    Returns
    -------
    SubmissionPublishResponse
        The submission's information and its restatements.
    """
    _session: AsyncSession
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

    async with db_manager.get_session() as _session:
        # Load the existing submission by name
        all_revisions = (
            await _session.scalars(
                select(SubmissionObj)
                .where(SubmissionObj.name == name)
                .order_by(SubmissionObj.revision.desc())
            )
        ).all()

        last_revision = all_revisions[-1]
        first_revision = all_revisions[0]

        if last_revision is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "submission": "No submission found for the given name."
                },
            )
        if last_revision.status != SubmissionObjStatusEnum.DRAFT:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "submission": (
                        "The latest revision for the requested submission is"
                        " not in draft state."
                    )
                },
            )

        # invalidate cache for this submission
        redis_key = cache.wis_keys.submission + str(last_revision.id)
        background_tasks.add_task(cache.del_pattern, redis_key)

        last_revision.status = SubmissionObjStatusEnum.PUBLISHED
        _session.add(last_revision)
        await _session.flush([last_revision])

        response = SubmissionPublishResponse.model_validate(
            last_revision, from_attributes=True
        )

        restatements: list[RestatementGetSimple] = []

        db_restatements = await _session.stream_scalars(
            select(Restatement).where(
                Restatement.group_id == first_revision.id
            )
        )

        async for restatement in db_restatements:
            restatements.append(
                RestatementGetSimple.model_validate(restatement)
            )

        response.restatements = restatements
        loader = SubmissionLoader(_session, static_cache, cache)
        manager = SubmissionManager(_session, static_cache, cache)
        await manager.save_aggregate(
            last_revision.id,
            (await loader.load(last_revision.id, db_only=True)).model_dump(
                mode="json"
            ),
            commit=True,
        )

        return response
