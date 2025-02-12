from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ColumnDef
from app.forms.attribute_reader.attribute_reader import AttributeReader
from app.schemas.column_def import AttributeType
from app.schemas.get_form import GetAttribute
from app.schemas.table_view import AttributeDefGetFull


class FormAttributeReader(AttributeReader):
    """
    Build form attributes
    """

    def get_supported_types(self) -> list[str]:
        """
        Return the list of column types this forms is responsible for
        :return: list of column types
        """
        return [AttributeType.FORM]

    async def read(
        self, attr_model: ColumnDef, session: AsyncSession
    ) -> Optional[GetAttribute | AttributeDefGetFull]:
        """
        Get the full schema of an attribute
        """

        # check sub-form
        if not attr_model.attribute_type_id:
            # undefined sub-form
            raise ValueError("missing reference to sub-form")

        # read basic attribute
        attr_def = await super().read(attr_model, session)

        # read sub-form definition
        from app.forms.form_reader import FormReader

        reader = FormReader(
            root_id=attr_model.attribute_type_id, context=self.reader_context
        )
        attr_def.form = await reader.read(session)

        return attr_def
