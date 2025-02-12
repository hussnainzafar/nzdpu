from app.forms.attribute_builder.attribute_builder import AttributeBuilder
from app.forms.attribute_builder.form_attribute_builder import (
    FormAttributeBuilder,
)
from app.schemas.column_def import AttributeType


class BoolOrNullAttributeBuilder(AttributeBuilder):
    """
    Build BoolOrNull attribute
    """

    def get_supported_types(self) -> list[str]:
        """
        Return the list of column types this forms is responsible for
        :return: list of column types
        """
        return [AttributeType.BOOL_OR_NULL]


class FloatOrNullAttributeBuilder(AttributeBuilder):
    """
    Build FloatOrNull attribute
    """

    def get_supported_types(self) -> list[str]:
        """
        Return the list of column types this forms is responsible for
        :return: list of column types
        """
        return [AttributeType.FLOAT_OR_NULL]


class FormOrNullAttributeBuilder(FormAttributeBuilder):
    """
    Build form or null attribute
    """

    def get_supported_types(self) -> list[str]:
        """
        Return the list of column types this forms is responsible for
        """
        return [AttributeType.FORM_OR_NULL]


class IntOrNullAttributeBuilder(AttributeBuilder):
    """
    Build int or null attribute
    """

    def get_supported_types(self) -> list[str]:
        """
        Return the list of column types this forms is responsible for
        """
        return [AttributeType.INT_OR_NULL]


class TextOrNullAttributeBuilder(AttributeBuilder):
    """
    Build TextOrNull attributes
    """

    def get_supported_types(self) -> list[str]:
        """
        Return the list of column types this forms is responsible for
        :return: list of column types
        """
        return [AttributeType.TEXT_OR_NULL]


class FileOrNullAttributeBuilder(AttributeBuilder):
    """
    Build FileOrNull attributes
    """

    def get_supported_types(self) -> list[str]:
        """
        Return the list of column types this forms is responsible for
        :return: list of column types
        """
        return [AttributeType.FILE_OR_NULL]
