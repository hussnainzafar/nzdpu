from sqlalchemy.ext.asyncio import AsyncSession

from app.forms.attribute_builder.attribute_builder import AttributeBuilder
from app.schemas.column_def import AttributeType
from app.schemas.create_form import CreateAttribute, CreateForm


class FormAttributeBuilder(AttributeBuilder):
    """
    Build form attributes
    """

    def get_supported_types(self) -> list[AttributeType]:
        """
        Return the list of column types this forms is responsible for
        :return: list of column types
        """
        return [AttributeType.FORM]

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

        # simply gets the sub-form from the spec
        sub_form_spec = spec.form
        assert sub_form_spec
        sub_form_spec.user_id = user_id

        return sub_form_spec

    async def build(
        self,
        spec: CreateAttribute,
        form_id: int,
        view_id: int,
        user_id: int,
        session: AsyncSession,
    ) -> int:
        """
        Build a form attribute
        """

        # check column type
        attribute_type: str = spec.type

        if attribute_type not in self.get_supported_types():
            raise ValueError(f"unexpected column type '{attribute_type}'")

        # check attribute definition doesn't exist already
        await self.check_duplicates(spec, form_id, session)

        from app.forms.form_builder import FormBuilder

        # creates the sub-form
        builder = FormBuilder(language_code=self.language_code)
        sub_form_spec = self.create_sub_form(spec, user_id)
        sub_form_id = await builder.build(
            spec=sub_form_spec, session=session, heritable=True
        )

        # creates the attribute
        return await self.create_attribute(
            spec=spec,
            form_id=form_id,
            view_id=view_id,
            user_id=user_id,
            session=session,
            attribute_type_id=sub_form_id,
        )
