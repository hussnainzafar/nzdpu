"""Column view schemas"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.constraint import Constraint, ConstraintCreate

# pylint: disable = too-few-public-methods, unsupported-binary-operation


class ColumnViewBase(BaseModel):
    """
    Base schema for column view
    """

    column_def_id: int
    table_view_id: int
    constraint_view: Any = None
    created_on: datetime | str = datetime.now()
    constraint_value: list[Constraint] = Field(default=[])
    user_id: Optional[int] = None
    permissions_set_id: Optional[int] = None
    choice_set_id: Optional[int] = None

    # pylint: disable=invalid-name,no-self-argument
    @field_validator("created_on")
    @classmethod
    def datetime_to_string(cls, v):
        """
        Converts datetime to string upon validation

        Parameters
        ----------
            v - the datetime value from the field
        Returns
        -------
            datetime converted to ISO8601 string
        """
        if isinstance(v, datetime):
            return v.isoformat()


class ColumnViewCreate(BaseModel):
    """
    Create schema for column view
    """

    column_def_id: int
    table_view_id: int
    constraint_view: Any = None
    created_on: datetime | str = datetime.now()
    constraint_value: list[ConstraintCreate] = Field(default=[])
    user_id: Optional[int] = None
    permissions_set_id: Optional[int] = None
    choice_set_id: Optional[int] = None


class ColumnViewGet(ColumnViewBase):
    """
    Column view schema
    """

    id: int
    model_config = ConfigDict(from_attributes=True)


class ColumnViewUpdate(BaseModel):
    """
    Update schema for column view
    """

    permissions_set_id: Optional[int] = None
    constraint_value: list[ConstraintCreate] | None = None
    constraint_view: Optional[Any] = None
    choice_set_id: Optional[int] = None


class TagConstraintViewItemAdditionalPropsModel(BaseModel):
    name_attribute_single: str = Field(default="", alias="nameAttributeSingle")
    other_choice_id: int = Field(default=0, alias="otherChoiceId")


class TagConstraintViewItemModel(BaseModel):
    additional_props: TagConstraintViewItemAdditionalPropsModel = Field(
        default=TagConstraintViewItemAdditionalPropsModel(),
        alias="additionalProps",
    )


class TagConstraintViewModel(BaseModel):
    item: TagConstraintViewItemModel = TagConstraintViewItemModel()


class ColumnConstraintViewRuleEnum(str, Enum):
    HIDE = "HIDE"
    SHOW = "SHOW"


class ColumnConstraintViewRuleSchemaModel(BaseModel):
    const: int = 0


class ColumnConstraintViewRuleConditionsModel(BaseModel):
    name: str = ""
    schema_: ColumnConstraintViewRuleSchemaModel = Field(
        default=ColumnConstraintViewRuleSchemaModel(), alias="schema"
    )


class ColumnConstraintViewRuleModel(BaseModel):
    effect: ColumnConstraintViewRuleEnum = ColumnConstraintViewRuleEnum.SHOW
    conditions: list[ColumnConstraintViewRuleConditionsModel] = [
        ColumnConstraintViewRuleConditionsModel()
    ]


class ColumnConstraintViewModel(BaseModel):
    rule: ColumnConstraintViewRuleModel = ColumnConstraintViewRuleModel()
