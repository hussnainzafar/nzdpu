from sqlalchemy.ext.asyncio import AsyncSession

from app.forms.attribute_builder.attribute_builder import AttributeBuilder
from app.schemas.column_def import AttributeType
from app.schemas.create_form import CreateAttribute


class SingleAttributeBuilder(AttributeBuilder):
    """
    Build single-select attributes
    """

    def get_supported_types(self) -> list[str]:
        """
        Return the list of column types this forms is responsible for
        """
        return [AttributeType.SINGLE]

    async def build(
        self,
        spec: CreateAttribute,
        form_id: int,
        view_id: int,
        user_id: int,
        session: AsyncSession,
    ) -> int:
        """
        Build a single attribute
        """

        # create column
        col_id: int = await super().build(
            spec, form_id, view_id, user_id, session
        )
        # create choices set
        await self.create_choices_set(
            choices=spec.choices, session=session, col_id=col_id
        )
        await session.flush()
        return col_id
