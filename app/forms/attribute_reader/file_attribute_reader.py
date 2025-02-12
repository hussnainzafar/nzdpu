from app.forms.attribute_reader.attribute_reader import AttributeReader
from app.schemas.column_def import AttributeType


class FileAttributeReader(AttributeReader):
    """
    Build file attributes
    """

    def get_supported_types(self) -> list[str]:
        """
        Return the list of column types this forms is responsible for
        :return: list of column types
        """
        return [AttributeType.FILE]
