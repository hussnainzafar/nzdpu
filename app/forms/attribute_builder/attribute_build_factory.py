from typing import Optional

from app.forms.attribute_builder.attribute_builder import AttributeBuilder
from app.forms.attribute_builder.composite_builder import (
    BoolOrNullAttributeBuilder,
    FileOrNullAttributeBuilder,
    FloatOrNullAttributeBuilder,
    FormOrNullAttributeBuilder,
    IntOrNullAttributeBuilder,
    TextOrNullAttributeBuilder,
)
from app.forms.attribute_builder.file_attribute_builder import (
    FileAttributeBuilder,
)
from app.forms.attribute_builder.form_attribute_builder import (
    FormAttributeBuilder,
)
from app.forms.attribute_builder.multiple_attribute_builder import (
    MultipleAttributeBuilder,
)
from app.forms.attribute_builder.primitive_attribute_builder import (
    PrimitiveAttributeBuilder,
)
from app.forms.attribute_builder.single_attribute_builder import (
    SingleAttributeBuilder,
)
from app.forms.form_meta import FormMeta
from app.schemas.column_def import AttributeType


class AttributeBuilderFactory:
    """
    A factory of attribute builders
    """

    @staticmethod
    def get_builder(attribute_type: str) -> Optional[AttributeBuilder]:
        """
        Return a builder
        :param attribute_type: type of attribute builder need
        :return: the requested builder, or None if not available
        """

        builder: Optional[AttributeBuilder] = None

        if attribute_type in FormMeta.primitive_types:
            builder = PrimitiveAttributeBuilder()
        elif attribute_type == AttributeType.SINGLE:
            builder = SingleAttributeBuilder()
        elif attribute_type == AttributeType.MULTIPLE:
            builder = MultipleAttributeBuilder()
        elif attribute_type == AttributeType.FILE:
            builder = FileAttributeBuilder()
        elif attribute_type == AttributeType.FORM:
            builder = FormAttributeBuilder()
        elif attribute_type == AttributeType.INT_OR_NULL:
            builder = IntOrNullAttributeBuilder()
        elif attribute_type == AttributeType.TEXT_OR_NULL:
            builder = TextOrNullAttributeBuilder()
        elif attribute_type == AttributeType.FLOAT_OR_NULL:
            builder = FloatOrNullAttributeBuilder()
        elif attribute_type == AttributeType.FORM_OR_NULL:
            builder = FormOrNullAttributeBuilder()
        elif attribute_type == AttributeType.BOOL_OR_NULL:
            builder = BoolOrNullAttributeBuilder()
        elif attribute_type == AttributeType.FILE_OR_NULL:
            builder = FileOrNullAttributeBuilder()

        return builder
