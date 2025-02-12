from app.forms.attribute_builder.attribute_builder import AttributeBuilder
from app.schemas.column_def import AttributeType


class FileAttributeBuilder(AttributeBuilder):
    """
    Build file attributes
    """

    def get_supported_types(self) -> list[str]:
        """
        Return the list of column types this forms is responsible for
        :return: list of column types
        """
        return [AttributeType.FILE]
