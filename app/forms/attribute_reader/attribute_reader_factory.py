from typing import Optional

from app.forms.attribute_reader.attribute_reader import AttributeReader
from app.forms.attribute_reader.composite_reader import (
    BoolOrNullAttributeReader,
    FileOrNullAttributeReader,
    FloatOrNullAttributeReader,
    FormOrNullAttributeReader,
    IntOrNullAttributeReader,
    TextOrNullAttributeReader,
)
from app.forms.attribute_reader.file_attribute_reader import (
    FileAttributeReader,
)
from app.forms.attribute_reader.form_attribute_reader import (
    FormAttributeReader,
)
from app.forms.attribute_reader.multiple_attribute_reader import (
    MultipleAttributeReader,
)
from app.forms.attribute_reader.primitive_attribute_reader import (
    PrimitiveAttributeReader,
)
from app.forms.attribute_reader.single_attribute_reader import (
    SingleAttributeReader,
)
from app.forms.form_meta import FormMeta
from app.schemas.column_def import AttributeType


class AttributeReaderFactory:
    """
    A factory of attribute readers
    """

    @staticmethod
    def get_reader(attribute_type: str) -> Optional[AttributeReader]:
        """
        Return an attribute reader
        :param attribute_type: type of attribute reader we need
        :return: the requested reader, or None if not available
        """

        builder: Optional[AttributeReader] = None

        if attribute_type in FormMeta.primitive_types:
            builder = PrimitiveAttributeReader()
        elif attribute_type == AttributeType.SINGLE:
            builder = SingleAttributeReader()
        elif attribute_type == AttributeType.MULTIPLE:
            builder = MultipleAttributeReader()
        elif attribute_type == AttributeType.FILE:
            builder = FileAttributeReader()
        elif attribute_type == AttributeType.FORM:
            builder = FormAttributeReader()
        elif attribute_type == AttributeType.INT_OR_NULL:
            builder = IntOrNullAttributeReader()
        elif attribute_type == AttributeType.TEXT_OR_NULL:
            builder = TextOrNullAttributeReader()
        elif attribute_type == AttributeType.FLOAT_OR_NULL:
            builder = FloatOrNullAttributeReader()
        elif attribute_type == AttributeType.FORM_OR_NULL:
            builder = FormOrNullAttributeReader()
        elif attribute_type == AttributeType.BOOL_OR_NULL:
            builder = BoolOrNullAttributeReader()
        elif attribute_type == AttributeType.FILE_OR_NULL:
            builder = FileOrNullAttributeReader()

        return builder
