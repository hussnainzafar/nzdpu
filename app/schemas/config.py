"""Config schema"""

from typing import Optional

from pydantic import BaseModel, model_validator
from typing_extensions import Self

from app.db.models import Config


class ConfigBase(BaseModel):
    """
    base schema for config
    """

    name: Optional[str] = None
    type: Optional[str] = None
    value: int | float | bool | Optional[str] = None
    description: Optional[str] = None

    @model_validator(mode="after")
    def cast_value_to_type(self) -> Self:
        match self.type:
            case Config.TYPE_INTEGER:
                if not isinstance(self.value, int):
                    self.value = int(self.value)
            case Config.TYPE_FLOAT:
                if not isinstance(self.value, float):
                    self.value = float(self.value)
            case Config.TYPE_BOOLEAN:
                if not isinstance(self.value, bool):
                    self.value = bool(self.value)
        return self


class ConfigGet(BaseModel):
    """
    Schema for get config
    """

    config: list[ConfigBase]


class UpdateConfigResponse(BaseModel):
    """
    Schema for update config
    """

    success: bool


class UpdateConfigRequest(BaseModel):
    """
    Schema for update config
    """

    general_system_email_address: Optional[str] = None
    data_explorer_download_all: int | Optional[str] = 0
    data_explorer_download_sample: int | Optional[str] = 1
    data_explorer_download_none: int | Optional[str] = 0
    company_profile_download_all: int | Optional[str] = 1
    company_profile_download_none: int | Optional[str] = 0
    data_download_show_all: int | Optional[str] = 1
    data_download_exclude_classification: int | Optional[str] = 1
    security_enable_captcha: Optional[bool] = True


class ConfigFeature(BaseModel):
    """
    base schema for config
    """

    data_explorer: list[str] | None = None
    company_profile: list[str] | None = None
    data_download: list[str] | None = None


class ConfigFeatureGet(BaseModel):
    """
    Schema for get config
    """

    config: list[ConfigFeature]
