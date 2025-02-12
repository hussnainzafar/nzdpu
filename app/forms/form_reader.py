"""Form reader"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import ColumnDef, TableDef
from app.forms.attribute_reader.attribute_reader import ReaderContext
from app.forms.attribute_reader.attribute_reader_factory import (
    AttributeReaderFactory,
)
from app.forms.attribute_reader.utils import object_as_dict
from app.schemas.get_form import GetForm, GetFormView
from app.schemas.table_view import FormGetFull, FormViewGetFull

# pylint: disable = too-many-locals


class FormReader:
    """
    Provides functionalities for reading forms
    """

    def __init__(self, root_id: int, context: str = ReaderContext.FORM_SCHEMA):
        """
        Initialize the reader
        Parameters
        ----------
        root_id - identifier of the root table
        context - reader context
        """

        self.root_id = root_id
        self.reader_context = context

    async def read(
        self, session: AsyncSession
    ) -> FormGetFull | GetForm | None:
        """
        Read the complete form schema definition corresponding to the current root table
        Parameters
        ----------
        session - database session

        Returns
        -------
        the form schema definition, or None if not found
        """

        form_schema: FormGetFull | GetForm | None = None

        # read root table
        result = await session.execute(
            select(TableDef)
            .options(selectinload(TableDef.views))
            .options(
                selectinload(TableDef.columns).selectinload(ColumnDef.views),
                selectinload(TableDef.columns).selectinload(ColumnDef.prompts),
            )
            .where(TableDef.id == self.root_id)
        )
        table_def = result.scalars().first()
        if table_def:
            # get basic table schema
            form_schema = (
                FormGetFull(**object_as_dict(table_def))
                if self.reader_context == ReaderContext.VIEW_SCHEMA
                else GetForm(**object_as_dict(table_def))
            )
            # get table views
            form_views = []
            for table_view in table_def.views:
                # get details of table view
                form_views.append(
                    FormViewGetFull(**object_as_dict(table_view))
                    if self.reader_context == ReaderContext.VIEW_SCHEMA
                    else GetFormView(**object_as_dict(table_view))
                )
            if form_views:
                # set table views
                form_schema.views = form_views
            # get attributes
            form_attrs = []
            for form_col in table_def.columns:
                # get attribute reader
                attribute_type = form_col.attribute_type
                reader = AttributeReaderFactory.get_reader(attribute_type)
                if not reader:
                    # reader not found
                    raise ValueError(
                        "could not find a reader for column type:"
                        f" '{attribute_type}"
                    )
                # read attribute
                reader.reader_context = self.reader_context
                form_attr = await reader.read(form_col, session)
                form_attrs.append(form_attr)
            if form_attrs:
                # set attributes
                form_schema.attributes = form_attrs
        return form_schema
