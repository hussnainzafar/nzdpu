"""Organization router"""

from enum import Enum
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from starlette import status

from app.db.models import User
from app.dependencies import (
    DbManager,
    StaticCache,
    get_current_user_or_none,
)
from app.loggers import get_nzdpu_logger
from app.routers.utils import (
    load_organization_by_lei,
)
from app.schemas.organization import (
    OrganizationGet,
    OrganizationGetWithNonLeiIdentifiers,
    OrganizationUpdate,
)
from app.service.organization_service import OrganizationService

# pylint: disable = too-many-locals

# creates the router
router = APIRouter(
    prefix="/external",
    tags=["external"],
    responses={404: {"description": "Not found"}},
)
logger = get_nzdpu_logger()


class OrganizationError(str, Enum):
    """
    Organization errors
    """

    NAME_TOO_SHORT = "The company name must be at least 1 character long."


@router.get(
    "/by-lei",
    response_model=OrganizationGet | OrganizationGetWithNonLeiIdentifiers,
)
async def get_organization_by_lei(
    db_manager: DbManager,
    static_cache: StaticCache,
    lei: Optional[str] = Query(None, description="legal entity identifier"),
    nzid: Optional[int] = Query(
        None, description="internal organization identifier"
    ),
    current_user: User = Depends(get_current_user_or_none),
):
    """
    Return the details of an organization by their LEI identifier

    Parameters
    ----------
        lei - legal entity identifier
        nz_id - internal organization identifier
    Returns
    -------
        organization data
    Raises
    ------
        HTTPException - If no organization matches the given LEI
    """
    if lei is None and nzid is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"lei_or_nzid": "LEI or NZID must be provided"},
        )

    orgs = await static_cache.organizations()
    if nzid is not None:
        org = orgs.get(nzid)
    else:
        org = next((org for org in orgs.values() if org.lei == lei), None)

    if org:
        return (
            OrganizationService.filter_non_lei_identifiers_based_on_user_role(
                org, current_user
            )
        )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"lei": f"No company found for {lei or nzid}"},
    )


@router.patch("/by-lei", response_model=OrganizationGet)
async def update_organization_by_lei(
    lei: str, organization_data: OrganizationUpdate, db_manager: DbManager
):
    """
    Return the details of an organization by their LEI identifier

    Parameters
    ----------
        id - legal entity identifier
        organization company type and website - company input data
    Returns
    -------
        organization data
    Raises
    ------
        HTTPException - If no organization matches the given LEI
    """
    async with db_manager.get_session() as _session:
        db_organization = await load_organization_by_lei(lei, _session)

        # update organization sent by the client
        organization_update = organization_data.model_dump(exclude_unset=True)
        for key, value in organization_update.items():
            setattr(db_organization, key, value)
        # save updated organization
        _session.add(db_organization)
        await _session.commit()
    return db_organization
