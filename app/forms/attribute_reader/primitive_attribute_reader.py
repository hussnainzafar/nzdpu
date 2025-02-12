from app.forms.attribute_reader.attribute_reader import AttributeReader
from app.forms.form_meta import FormMeta
from app.schemas.column_def import AttributeType


class PrimitiveAttributeReader(AttributeReader):
    """
    Read primitive attributes
    """

    def get_supported_types(self) -> list[AttributeType]:
        """
        Return the list of column types this forms is responsible for
        :return: list of column types
        """
        return FormMeta.primitive_types
