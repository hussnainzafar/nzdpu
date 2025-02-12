"""Restatement schemas"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

# pylint: disable = too-few-public-methods, unsupported-binary-operation


class RestatementsBase(BaseModel):
    """
    Base schema for Restatements
    """

    nz_id: int


class AttributePathChoiceSection(BaseModel):
    """
    Schema for attribute paths, choice section
    """

    field: Optional[str] = None
    value: Optional[int] = None
    index: int = 0

    def __repr__(self):
        return ":".join(
            [
                str(x) if x is not None else ""
                for x in [self.field, self.value, self.index]
            ]
        )

    def __str__(self):
        return self.__repr__()


class AttributePathsModel(BaseModel):
    """
    Schema for updated attributes path through forms.

    It can recursively contain an object of the same form, to specify
    paths of subforms.
    """

    form: Optional[str] = Field(default="")
    choice: AttributePathChoiceSection = AttributePathChoiceSection()
    row_id: int = Field(default=0)
    attribute: str
    sub_path: Optional[AttributePathsModel] = None

    def clone(self, attribute: str = ""):
        path = None
        if self.sub_path is not None:
            path = AttributePathsModel(
                form=self.form,
                choice=self.choice,
                row_id=self.row_id,
                attribute=attribute or self.attribute,
                sub_path=self.sub_path.clone(attribute=attribute),
            )
        path = AttributePathsModel(
            form=self.form,
            choice=self.choice,
            row_id=self.row_id,
            attribute=attribute or self.attribute,
        )

        return path

    @classmethod
    def unpack_field_path(cls, field_path: str) -> AttributePathsModel:
        """
        Helps to "unpack" the path to the value of a field  in a nested
        structure.

        The syntax used for this is in the way of:
        <form>.{<choice_field>:<choice_value>:<index>}.<attribute>
        where <index> is the index in the list of elements for two
        elements with the same choice_field and choice_value, and
        <attribute> is the final leaf where to get the value from.
        The part before <attribute> can be repeated indefinetly to
        indicate more deeply nested structures.

        Args:
            field_path (str): It's the path in the format specified above.

        Raises:
            HTTPException: Format check on field_path

        Returns:
            AttributePathsModel: A custom model holding the information
                from the "path" syntax into something usable in Python.
        """
        *whole_path, attribute = field_path.split(".")
        path = cls(attribute=attribute)
        if whole_path:  # empty list on root-level attributes
            sub_path = None
            for i in range(len(whole_path) - 1, 0, -2):
                # we must get path sections starting from the end of the
                # path going backwards, in groups of two moving forwards
                form = whole_path[i - 1]
                try:
                    field, choice, index = whole_path[i].strip("{}").split(":")
                except ValueError as exc:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "restatements": (
                                f"Wrong attribute field path: '{field_path}'"
                            )
                        },
                    ) from exc
                if (
                    choice and not field  # choice should always have parent
                ) or not index:  # and index should always be valued
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "restatements": (
                                f"Malformed field path: '{field_path}'"
                            )
                        },
                    )
                if not choice and not field and index:
                    choice = None
                    field = None
                    index = int(index)
                else:
                    choice = int(choice)
                    field = field
                    index = int(index)
                path = cls(
                    form=form,
                    choice=AttributePathChoiceSection(
                        field=field, value=choice, index=index
                    ),
                    attribute=attribute,
                )
                # set sub_path as the path stored in previous iteration
                path.sub_path = sub_path
                # store the defined path object to use it as sub_path
                # in the next iterations
                sub_path = path

        return path

    def __repr__(self):
        if self.form and any(
            [x or x == 0 for x in self.choice.model_dump().values()]
        ):
            r = ".".join(
                [
                    x
                    for x in [self.form, f"{{{self.choice.__repr__()}}}"]
                    if x is not None
                ]
            )
        else:
            r = ""
        sb = self.sub_path
        while sb is not None:
            r += "." + sb.__repr__()
            sb = sb.sub_path
        if self.sub_path is None:
            r += "." if r else ""
            r += self.attribute
        return r

    def __str__(self):
        return self.__repr__()

    def startswith(self, __value) -> bool:
        return self.__str__().startswith(__value)

    def endswith(self, __value) -> bool:
        return self.__str__().endswith(__value)

    def __hash__(self) -> int:
        return hash(self.__str__())

    def __eq__(self, __value: str) -> bool:
        return self.__str__() == __value

    def __ne__(self, __value: str) -> bool:
        return self.__str__() != __value

    def __gt__(self, __value: str) -> bool:
        return self.__str__() > __value

    def __lt__(self, __value: str) -> bool:
        return self.__str__() < __value


AttributePathsModel.model_rebuild()


class RestatementList(BaseModel):
    """
    List schema for Restatement
    """

    reporting_year: int
    reported_on: datetime
    value: Any
    reason: str | None = None
    disclosure_source: str | None = None


class RestatementAttributePrompt(BaseModel):
    """
    Attribute prompt schema for Restatement
    """

    name: str
    prompt: str


RestatementOriginal = RestatementList


class RestatementGet(RestatementsBase):
    """
    Get schema for Restatement
    """

    attribute: RestatementAttributePrompt
    original: RestatementOriginal
    restatements: list[RestatementList]


class RestatementCreate(BaseModel):
    """
    Create schema for Restatement
    """

    path: str
    reason: str
    value: Any = None


class RestatementGetSimple(BaseModel):
    """
    Schema to get restatement from the DB
    """

    attribute_name: Optional[str] = None
    attribute_row: Optional[int] = None
    reason_for_restatement: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)
