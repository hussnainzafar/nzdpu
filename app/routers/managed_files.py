"""Managed Files router"""

import base64
import uuid
from datetime import timedelta

import requests
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from google import auth
from google.auth.transport import requests
from google.cloud import storage
from sqlalchemy import func, select
from starlette import status

import app.settings as settings
from app.constraint_validator import ConstraintValidator
from app.db.models import AuthRole, ColumnDef, FileRegistry, User, Vault
from app.dependencies import (
    DbManager,
    RoleAuthorization,
    get_current_user_or_none,
    initialize_firebase_storage_client,
)
from app.routers.utils import update_user_data_last_accessed
from app.schemas.managed_file import FileCreate, FileGet, FileGetResponse

# authentication scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# creates the router
router = APIRouter(
    prefix="/files",
    tags=["file_registry"],
    responses={404: {"description": "Not found"}},
)


async def validate_constraints(file: FileCreate, session):
    stmt = select(ColumnDef).filter_by(name="upload_cert")
    column = await session.scalar(stmt)
    if not column:
        raise HTTPException(
            status_code=404,
            detail={"column": "Column not found"},
        )
    constraints = column.views[0].constraint_value
    if constraints:
        constraint_validator = ConstraintValidator(
            constraints=constraints, value=file.base64, column=column
        )
        constraint_validator.validate()


@router.post("", response_model=FileGet)
async def create_file(
    file: FileCreate,
    db_manager: DbManager,
    current_user: User = Depends(
        RoleAuthorization(
            [AuthRole.DATA_PUBLISHER, AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR]
        )
    ),
):
    """
    Create and upload a new managed file

    Returns
    -------
    new file

    """

    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        # replace None vault_obj_id with DEFAULT_BUCKET specified in settings.py
        if file.vault_obj_id == "":
            if (
                settings.gcp.default_bucket is None
                or settings.gcp.default_bucket == ""
            ):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Default Bucket has no value",
                )
            file.vault_obj_id = settings.gcp.default_bucket
        # if there is no given vault_path, give a randomly generated UUID instead
        if file.vault_path == "":
            file.vault_path = "nzdpu_" + str(uuid.uuid4())
        # if value_id is left blank, as 0, find the highest value_id in the registry and add one
        if not file.value_id:
            max_value_id_query = select(func.max(FileRegistry.value_id))
            max_value_id_result = await _session.execute(max_value_id_query)
            max_value_id = max_value_id_result.scalar() or 0
            file.value_id = max_value_id + 1

        vault_id = file.vault_id if file.vault_id else 0
        if vault_id == 0:
            vault = await _session.execute(
                select(Vault).order_by(Vault.id).limit(1)
            )
            vault = vault.scalar_one_or_none()
            if vault:
                vault_id = vault.id
            else:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Cannot find a vault to store the file in",
                )
        else:
            vault = await _session.execute(
                select(Vault).filter_by(id=vault_id)
            )
            vault = vault.scalar_one_or_none()
            if not vault:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Vault with ID {vault_id} does not exist",
                )
        # validate file constraints
        await validate_constraints(file, _session)
        db_file = FileRegistry(
            value_id=file.value_id,
            vault_id=vault_id,
            view_id=file.view_id,
            vault_obj_id=file.vault_obj_id,
            vault_path=file.vault_path,
        )

        client = storage.Client()
        try:
            base_decoded = base64.b64decode(file.base64)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Base64 format is incorrect",
            ) from exc
        _session.add(db_file)
        bucket = client.get_bucket(file.vault_obj_id)
        file_dest = bucket.blob(file.vault_path)
        file_dest.upload_from_string(base_decoded)
        await _session.commit()
        return db_file


# def retrieve_email_from_metadata() -> str | None:
#     try:
#         req = requests.get('GET',
#           'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email',
#                            headers={'Metadata-Flavor': "Google"})
#     except Exception:
#         # We failed to connect to the metadata server, returning None
#         return
#     if req.status_code == 200:
#         return req.content.decode()


# def get_service_account():
#     if sa := os.environ.get('DEFAULT_SERVICE_ACCOUNT_EMAIL'):
#         return sa
#     if sa := retrieve_email_from_metadata():
#         return sa
#     raise RuntimeError("'DEFAULT_SERVICE_ACCOUNT_EMAIL' needs to be defined or we were unable to resolve the "
#                        "email via metadata server")


def create_download_url(
    file: str,
    fb_admin_storage_client: storage.Bucket,
    expiration: timedelta | None = None,
):
    # check if URL has no specified expiration time
    if expiration is None:
        expiration = timedelta(hours=1)
    credentials, _ = auth.default()
    # check if the token is empty, if so refresh and get a new token
    if credentials.token is None:
        credentials.refresh(requests.Request())
    # retrieve blob and return signed url
    blob = fb_admin_storage_client.blob(file)
    signed_url = blob.generate_signed_url(
        version="v4",
        expiration=expiration,
        service_account_email=GCP_DEFAULT_SERVICE_ACCOUNT_EMAIL,
        access_token=credentials.token,
        method="GET",
    )

    return signed_url


@router.get("/{file_id}", response_model=FileGetResponse)
async def get_file(
    file_id: int,
    db_manager: DbManager,
    fb_admin_storage_client=Depends(initialize_firebase_storage_client),
    current_user=Depends(get_current_user_or_none),
):
    """
    Return the details of a specified file
    -------
        list of file details
    """

    if current_user:
        async with db_manager.get_session() as _session:
            # Update user.data_last_accessed for keeping track of inactivity
            await update_user_data_last_accessed(
                session=_session, current_user=current_user
            )
    async with db_manager.get_session() as _session:
        # search file registry by id
        db_file = await _session.scalar(
            select(FileRegistry).where(FileRegistry.id == file_id)
        )
        if not db_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No file with an id of {file_id} was found",
            )
        file = FileGet.model_validate(db_file)
        with fb_admin_storage_client as _storage:
            signed_url = create_download_url(
                file=file.vault_path,
                fb_admin_storage_client=_storage,
            )

        return FileGetResponse(signed_url=signed_url, **file.model_dump())


@router.get("", response_model=list[FileGet])
async def list_files(
    view_id: int,
    db_manager: DbManager,
    current_user=Depends(get_current_user_or_none),
):
    """
    Return the list of files by view ID

    Returns
    -------
        list of files containing a specific view ID
    """
    # print(f"VIEW_ID: {view_id}")

    # search file registry by view_id
    stmt = select(FileRegistry).filter_by(view_id=view_id)

    async with db_manager.get_session() as _session:
        if current_user:
            # Update user.data_last_accessed for keeping track of inactivity
            await update_user_data_last_accessed(
                session=_session, current_user=current_user
            )
        result = await _session.execute(stmt)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No files with a view id of {view_id} were found",
            )
    files = result.scalars().all()
    # print(files)
    return files
