"""Vaults router"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from starlette import status

from app.db.models import User, Vault
from app.dependencies import DbManager, get_current_user
from app.routers.utils import update_user_data_last_accessed
from app.schemas.vault import VaultGet

# authentication scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# creates the router
router = APIRouter(
    prefix="/files/vaults",
    tags=["vaults"],
    dependencies=[Depends(oauth2_scheme)],
    responses={404: {"description": "Not found"}},
)


@router.get("", response_model=list[VaultGet])
async def list_vaults(
    db_manager: DbManager, current_user: User = Depends(get_current_user)
):
    """
    Return the list of vaults

    Returns
    -------
        list of vaults
    """
    # load vaults
    stmt = select(Vault)
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        result = await _session.execute(stmt)
    return result.scalars().all()


@router.get("/{vault_id}", response_model=VaultGet)
async def get_vault(
    vault_id: int,
    db_manager: DbManager,
    current_user: User = Depends(get_current_user),
):
    """
    Return the details of a vault

    Parameters
    ----------
        id - vault identifier
    Returns
    -------
        vault details
    """
    # load vault
    async with db_manager.get_session() as _session:
        # Update user.data_last_accessed for keeping track of inactivity
        await update_user_data_last_accessed(
            session=_session, current_user=current_user
        )

        db_vault = await _session.get(Vault, vault_id)
    if db_vault is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"vault_id": "Vault not found"},
        )

    return db_vault
