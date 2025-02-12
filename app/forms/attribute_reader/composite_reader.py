from app.forms.attribute_reader.attribute_reader import AttributeReader
from app.forms.attribute_reader.form_attribute_reader import (
    FormAttributeReader,
)
from app.schemas.column_def import AttributeType


class BoolOrNullAttributeReader(AttributeReader):
    """
    Read bool_or_null attributes
    """

    def get_supported_types(self) -> list[str]:
        """
        Return the list of column types this reader is responsible for
        :return: list of column types
        """
        return [AttributeType.BOOL_OR_NULL]


class FloatOrNullAttributeReader(AttributeReader):
    """
    Read float_or_null attributes
    """

    def get_supported_types(self) -> list[str]:
        """
        Return the list of column types this reader is responsible for
        :return: list of column types
        """
        return [AttributeType.FLOAT_OR_NULL]


class FormOrNullAttributeReader(FormAttributeReader):
    """
    Read form or null attribute
    """

    def get_supported_types(self) -> list[AttributeType]:
        """
        Return the list of column types this forms is responsible for
        :return: list of column types
        """
        return [AttributeType.FORM_OR_NULL]


class IntOrNullAttributeReader(AttributeReader):
    """
    Read int or null attribute
    """

    def get_supported_types(self) -> list[AttributeType]:
        """
        Return the list of column types this forms is responsible for
        :return: list of column types
        """
        return [AttributeType.INT_OR_NULL]


class TextOrNullAttributeReader(AttributeReader):
    """
    Read text_or_null attributes
    """

    def get_supported_types(self) -> list[str]:
        """
        Return the list of column types this reader is responsible for
        :return: list of column types
        """
        return [AttributeType.TEXT_OR_NULL]


class FileOrNullAttributeReader(AttributeReader):
    """
    Read file_or_null attributes
    """

    def get_supported_types(self) -> list[str]:
        """
        Return the list of column types this reader is responsible for
        :return: list of column types
        """
        return [AttributeType.FILE_OR_NULL]
