"""Config router"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import AuthRole, Config, ConfigProperty
from app.dependencies import DbManager, RoleAuthorization, oauth2_scheme
from app.schemas.config import (
    ConfigBase,
    ConfigFeature,
    ConfigFeatureGet,
    ConfigGet,
    UpdateConfigRequest,
    UpdateConfigResponse,
)

from .utils import update_user_data_last_accessed

# pylint: disable = too-many-locals

# creates the router
router = APIRouter(
    prefix="/config",
    tags=["config"],
    responses={404: {"config": "Not found"}},
    include_in_schema=False,
)


@router.get("", response_model=ConfigGet)
async def get_config(db_manager: DbManager):
    """
    Retrieve application configuration.

    This endpoint returns a list of configuration settings.

    Args:
        session (Session): The SQLAlchemy database session.

    Returns:
        dict: A dictionary containing the configuration settings.
    """

    try:
        async with db_manager.get_session() as _session:
            result = await _session.execute(select(Config))
            configs = result.scalars().all()

        # Extract attributes from Config instances and create dictionaries
        config_dicts = [
            {
                "name": config.name,
                "type": config.type,
                "value": config.value,
                "description": config.description,
            }
            for config in configs
        ]

        # Create instances of ConfigBase from the dictionaries
        config_bases = [
            ConfigBase(**config_dict) for config_dict in config_dicts
        ]

        for each in config_bases:
            each.name = each.name.replace(".", "_")

        return {"config": config_bases}

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=404,
            detail={"Error": f"Database error occurred {e}"},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=404, detail=f"An unexpected error occurred {e}"
        ) from e


@router.get("/features", response_model=ConfigFeatureGet)
async def get_config_features(
    db_manager: DbManager, token: str = Depends(oauth2_scheme)
):
    """
    Retrieve application enabled configuration.

    This endpoint returns a list of configuration settings.

    Args:
        session (Session): The SQLAlchemy database session.
        token (str): The OAuth2 token for authentication.

    Returns:
        dict: A dictionary containing the configuration settings.
    """

    try:
        async with db_manager.get_session() as _session:
            result = await _session.execute(select(Config))
            configs = result.scalars().all()

        # Extract attributes from Config instances and create dictionaries
        config_dicts = [
            {"name": config.name, "value": config.value} for config in configs
        ]
        list_of_response_key = [
            "data_explorer",
            "company_profile",
            "data_download",
        ]
        final_respnse = [
            {
                "data_explorer": [],
                "company_profile": [],
                "data_download": [],
            }
        ]
        for each in config_dicts:
            if each["value"] == "1" or each["value"] == "True":
                name = each["name"].split(".") if each["name"] else None
                if name:
                    if name[0] in list_of_response_key:
                        final_respnse[0][name[0]].append(
                            f"{name[0]}_{name[1]}"
                        )

        # Create instances of ConfigBase from the dictionaries
        config_bases = [
            ConfigFeature(**config_dict) for config_dict in final_respnse
        ]

        return {"config": config_bases}

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=404,
            detail={"Error": f"Database error occurred {e}"},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=404, detail=f"An unexpected error occurred {e}"
        ) from e


@router.patch("", response_model=UpdateConfigResponse)
async def update_config(
    config_updates: UpdateConfigRequest,
    db_manager: DbManager,
    current_user=Depends(
        RoleAuthorization([AuthRole.ADMIN, AuthRole.SCHEMA_EDITOR])
    ),
):
    """
    Update application configuration.

    This endpoint allows updating configuration settings.

    Args:
        config_updates (dict): A dictionary containing configuration updates.
        session (Session): The SQLAlchemy database session.
        token (str): The OAuth2 token for authentication.

    Returns:
        dict: A dictionary indicating the success of the operation.
    """

    try:
        key_to_config_property = {
            "general_system_email_address": (
                ConfigProperty.GENERAL_SYSTEM_EMAIL_ADDRESS
            ),
            "data_explorer_download_all": (
                ConfigProperty.DATA_EXPLORER_DOWNLOAD_ALL
            ),
            "data_explorer_download_sample": (
                ConfigProperty.DATA_EXPLORER_DOWNLOAD_SAMPLE
            ),
            "data_explorer_download_none": (
                ConfigProperty.DATA_EXPLORER_DOWNLOAD_NONE
            ),
            "company_profile_download_all": (
                ConfigProperty.COMPANY_PROFILE_DOWNLOAD_ALL
            ),
            "company_profile_download_none": (
                ConfigProperty.COMPANY_PROFILE_DOWNLOAD_NONE
            ),
            "data_download_show_all": ConfigProperty.DATA_DOWNLOAD_SHOW_ALL,
            "data_download_exclude_classification": (
                ConfigProperty.DATA_DOWNLOAD_EXCLUDE_CLASSIFICATION
            ),
            "security_enable_captcha": ConfigProperty.SECURITY_ENABLE_CAPTCHA,
        }

        async with db_manager.get_session() as _session:
            # Update user.data_last_accessed for keeping track of inactivity
            await update_user_data_last_accessed(
                session=_session, current_user=current_user
            )

            config_updates = config_updates.dict(exclude_unset=True)

            update_successful = False  # Flag to track if any updates were made

            for key, value in config_updates.items():
                # Check if the configuration property exists
                config_property = key_to_config_property.get(key)

                if config_property:
                    # Use the config_property value as the name of the configuration property
                    name_of_rec = config_property.value

                    filter_condition = Config.name == name_of_rec

                    select_query = select(Config.id).filter(filter_condition)
                    get_id = await _session.execute(select_query)
                    configs_id = get_id.scalars().first()
                    config = await _session.get(Config, configs_id)

                    if config:
                        # Update the configuration property value
                        config.value = str(value)
                        update_successful = True

            if update_successful:
                await _session.commit()
                return {"success": True}
            return {"success": False}

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=500, detail={"Error": f"Database error occurred {e}"}
        ) from e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"Error": f"An unexpected error occurred: {str(e)}"},
        ) from e
