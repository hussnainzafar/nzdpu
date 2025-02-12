from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Choice, ColumnDef
from app.forms.attribute_reader.form_attribute_reader import (
    FormAttributeReader,
)
from app.forms.attribute_reader.utils import object_as_dict
from app.schemas.choice import ChoiceGet
from app.schemas.column_def import AttributeType
from app.schemas.get_form import GetAttribute
from app.schemas.table_view import AttributeDefGetFull


class MultipleAttributeReader(FormAttributeReader):
    """
    Build multiple attributes
    """

    def get_supported_types(self) -> list[str]:
        """
        Return the list of column types this forms is responsible for
        """
        return [AttributeType.MULTIPLE]

    async def read(
        self, attr_model: ColumnDef, session: AsyncSession
    ) -> Optional[GetAttribute | AttributeDefGetFull]:
        """
        Get the full schema of an attribute
        """

        # check choice set
        if not attr_model.choice_set_id:
            # undefined choices set
            raise ValueError("undefined choices set")

        # read basic attribute
        attr_def = await super().read(attr_model, session)

        # load choices
        set_id: int = attr_model.choice_set_id
        result = await session.execute(
            select(Choice).where(Choice.set_id == set_id)
        )
        choices = result.scalars().all()
        attr_def.choices = [
            ChoiceGet(**object_as_dict(choice)) for choice in choices
        ]

        return attr_def
