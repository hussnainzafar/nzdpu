"""Attribute reader"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ColumnDef
from app.forms.attribute_reader.utils import object_as_dict
from app.schemas.get_form import GetAttribute, GetAttributeView
from app.schemas.prompt import AttributePromptGet
from app.schemas.table_view import AttributeDefGetFull, AttributeViewGetFull


class ReaderContext(str, Enum):
    """
    Context of a reader
    """

    FORM_SCHEMA = "schema"
    VIEW_SCHEMA = "view"


# pylint: disable = not-callable


class AttributeReader(ABC):
    """
    An abstract attribute reader. Concrete readers inherit from it.
    """

    def __init__(self, context: str = ReaderContext.FORM_SCHEMA):
        """
        Initialize the reader
        Parameters
        ----------
        context - reader context
        """

        self.reader_context = context

    @abstractmethod
    def get_supported_types(self) -> list[str]:
        """
        Return the list of attribute types this forms is responsible for
        :return: list of attribute types
        """

    async def read(
        self, attr_model: ColumnDef, session: AsyncSession
    ) -> Optional[GetAttribute | AttributeDefGetFull]:
        """
        Get the full schema of an attribute
        Parameters
        ----------
        attr_model - attribute model
        session - database session

        Returns
        -------
        the attribute schema definition, or None if not found
        """

        # check type
        attribute_type: str = attr_model.attribute_type
        if attribute_type not in self.get_supported_types():
            raise ValueError(f"unexpected attribute type '{attribute_type}'")

        # get basic column schema
        attr_def = (
            AttributeDefGetFull(**object_as_dict(attr_model))
            if self.reader_context == ReaderContext.VIEW_SCHEMA
            else GetAttribute(**object_as_dict(attr_model))
        )

        if self.reader_context == ReaderContext.FORM_SCHEMA:
            # get attribute views
            attr_views = []
            for col_view in attr_model.views:
                # get details of attribute view
                attr_view = (
                    AttributeViewGetFull(
                        **object_as_dict(col_view), column_def=attr_def
                    )
                    if self.reader_context == ReaderContext.VIEW_SCHEMA
                    else GetAttributeView(**object_as_dict(col_view))
                )
                # append attribute view
                attr_views.append(attr_view)
            if attr_views:
                # set attribute views
                attr_def.views = attr_views

        # get attribute prompts
        attr_prompts = []
        for prompt in attr_model.prompts:
            # get details of attribute prompt
            attr_prompt = AttributePromptGet(**object_as_dict(prompt))
            # append attribute prompt
            attr_prompts.append(attr_prompt)
        if attr_prompts:
            # set attribute prompts
            attr_def.prompts = attr_prompts

        return attr_def
