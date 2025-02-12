"""Constraint schemas"""

from enum import Enum

from pydantic import BaseModel, Field

# pylint: disable = too-few-public-methods, unsupported-binary-operation


class ConstraintConditionTarget(str, Enum):
    """
    Target for a constraint condition
    """

    ATTRIBUTE = "attribute"
    VIEW = "view"


class ConstraintCondition(BaseModel):
    """
    A condition in a constraint
    """

    target: ConstraintConditionTarget = ConstraintConditionTarget.ATTRIBUTE
    set: dict = Field(default={})


class ConstraintAction(BaseModel):
    """
    An action in a constraint
    """

    set: dict = Field(default={})


class Constraint(BaseModel):
    """
    View constraint component of CreateForm schema
    """

    code: str
    conditions: list[ConstraintCondition] = Field(default=[])
    actions: list[ConstraintAction] = Field(default=[])


class ConstraintCreate(Constraint):
    """
    Create schema for constraint
    """
