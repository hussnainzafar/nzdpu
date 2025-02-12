"""Choice schemas"""

from typing import Annotated, Any, List, Optional

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    field_validator,
)

from .enums import SortOrderEnum

# pylint: disable = too-few-public-methods, unsupported-binary-operation, no-self-argument


def validate_label_not_empty(value: str) -> str:
    if not value or value.strip() == "":
        raise ValueError("Label should not be empty")
    return value


class ChoiceBase(BaseModel):
    """
    Base schema for choice
    """

    set_name: str
    value: str
    description: Optional[str] = None
    set_id: Optional[int] = None
    language_code: Optional[str] = "en_US"
    order: Optional[int] = 1


class ChoiceCreate(ChoiceBase):
    """
    Create schema for choice
    """

    choice_id: Optional[int] = None


class ChoiceGet(ChoiceBase):
    """
    Choice schema
    """

    id: int
    choice_id: int
    model_config = ConfigDict(from_attributes=True)


class PaginationResponse(BaseModel):
    """
    Pagination response schema
    """

    start: int
    end: int
    total: int
    items: List[ChoiceGet]


class ChoiceUpdate(BaseModel):
    """
    Update schema for choice
    """

    value: Optional[str] = None
    description: Optional[str] = None
    order: Optional[int] = None


class ChoiceCreateSet(BaseModel):
    """
    Create schema for a set of choices.
    """

    labels: list[Annotated[str, BeforeValidator(validate_label_not_empty)]]
    set_name: str
    language_code: Optional[str] = "en_US"

    @field_validator("labels")
    @classmethod
    def check_duplicates(cls, labels):
        """
        Check if there are duplicate labels in the set.

        Args:
            labels (list[str]): The list of labels to be checked.

        Raises:
            ValueError: If there are duplicate labels in the set.

        Returns:
            list[str]: The validated list of labels.
        """
        if len(labels) != len(set(labels)):
            raise ValueError(
                "Labels should not have duplicates within the same set"
            )
        if len(labels) == 0:
            raise ValueError("Labels should not be an empty list")
        return labels


class ChoiceSetBase(BaseModel):
    """
    Choice schema
    """

    id: int
    value: str
    order: int = 1
    language_code: str = "en_US"
    description: Optional[str] = None
    choice_id: Optional[int] = None


class ChoiceSet(BaseModel):
    """
    Choice set schema
    """

    set_id: int
    set_name: str
    choices: List[ChoiceSetBase]


class ChoiceSetPaginationResponse(BaseModel):
    """
    Pagination response schema
    """

    start: int
    end: int
    total: int
    items: List[ChoiceSet]


class ChoiceSetResponse(BaseModel):
    """
    Choice set response schema
    """

    set_id: int
    set_name: str
    language_code: str
    labels: List[str]
    model_config = ConfigDict(from_attributes=True)


class ListChoiceFilterByModel(BaseModel):
    """
    Schema for list choice 'filter_by' parameter
    """

    choice_id: Optional[int] = None
    set_id: Optional[int] = None
    value: Optional[Any] = None


class ListChoiceOrderByModel(BaseModel):
    """
    Schema for list choice 'order_by' parameter.
    """

    id: Optional[int] = None
    choice_id: Optional[int] = None
    set_id: Optional[int] = None
    value: Optional[Any] = None
    order: Optional[SortOrderEnum] = None
    model_config = ConfigDict(extra="forbid")


class ChoiceCreateSetResponse(BaseModel):
    """
    Schema for creating a choice set.
    """

    set_id: int
