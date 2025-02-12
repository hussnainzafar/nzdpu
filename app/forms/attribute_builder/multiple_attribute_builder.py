from sqlalchemy.ext.asyncio import AsyncSession

from app.forms.attribute_builder.form_attribute_builder import (
    FormAttributeBuilder,
)
from app.schemas.column_def import AttributeType
from app.schemas.create_form import CreateAttribute, CreateForm, CreateFormView


class MultipleAttributeBuilder(FormAttributeBuilder):
    """
    Build multi-select attributes
    """

    def get_supported_types(self) -> list[AttributeType]:
        """
        Return the list of column types this forms is responsible for
        """
        return [AttributeType.MULTIPLE]

    def create_sub_form(
        self, spec: CreateAttribute, user_id: int
    ) -> CreateForm:
        """
        Creates a sub-form for holding the value types of this attribute
        Parameters
        ----------
        spec - attribute specification
        user_id - user identifier
        Returns
        -------
        the sub-form specification
        """

        # general form data
        sub_form_name: str = f"{spec.name}_form"
        sub_form_description: str = f"Form for {spec.name}"
        # default view
        sub_view_name: str = f"{spec.name}_view"
        sub_view_description: str = f"View for {spec.name}"
        sub_view = CreateFormView(
            name=sub_view_name, description=sub_view_description
        )
        # default attributes for holding
        # choice selection (int) and extra values (text)
        sub_form_attributes: list[CreateAttribute] = [
            CreateAttribute(type=AttributeType.INT, name=f"{spec.name}_int"),
            CreateAttribute(type=AttributeType.TEXT, name=f"{spec.name}_text"),
        ]
        return CreateForm(
            name=sub_form_name,
            description=sub_form_description,
            user_id=user_id,
            view=sub_view,
            attributes=sub_form_attributes,
        )

    async def build(
        self,
        spec: CreateAttribute,
        form_id: int,
        view_id: int,
        user_id: int,
        session: AsyncSession,
    ) -> int:
        """
        Build a multiple attribute
        """

        # create attribute
        col_id: int = await super().build(
            spec, form_id, view_id, user_id, session
        )
        # create choices set
        await self.create_choices_set(
            choices=spec.choices, session=session, col_id=col_id
        )
        # bind column to choices set
        return col_id
