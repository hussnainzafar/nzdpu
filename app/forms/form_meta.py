"""Form meta"""

from sqlalchemy import Boolean, DateTime, Float, Integer, Text

from app.db.types import (
    BoolOrNullType,
    FileOrNullType,
    FloatOrNullType,
    FormOrNullType,
    IntOrNullType,
    TextOrNullType,
)
from app.schemas.column_def import AttributeType


class FormMeta:
    """
    Schema meta data, constants and utilities
    """

    # table names
    t_nzdpu_form: str = "nzdpu_form"
    t_wis_obj: str = "wis_obj"

    # field names
    f_id: str = "id"
    f_name: str = "name"
    f_obj_id: str = "obj_id"
    f_user_id: str = "user_id"
    f_submitted_by: str = "submitted_by"
    f_value_id: str = "value_id"
    f_date_end_reporting_year: str = "date_end_reporting_year"
    f_reporting_year: str = "reporting_year"

    # field values
    primitive_types = [
        AttributeType.LABEL,
        AttributeType.TEXT,
        AttributeType.BOOL,
        AttributeType.INT,
        AttributeType.FLOAT,
        AttributeType.DATETIME,
    ]

    @staticmethod
    def get_column_type(attribute_type: str):
        """
        Return the database column type corresponding to an attribute
        :param attribute_type: the attribute type
        :return: the column type, or None if the attribute does not
            require a data column
        """

        column_type = None

        if attribute_type == AttributeType.TEXT:
            column_type = Text
        elif attribute_type == AttributeType.BOOL:
            column_type = Boolean
        elif attribute_type in [
            AttributeType.INT,
            AttributeType.SINGLE,
            AttributeType.MULTIPLE,
            AttributeType.FORM,
            AttributeType.FILE,
        ]:
            column_type = Integer
        elif attribute_type == AttributeType.FLOAT:
            column_type = Float
        elif attribute_type == AttributeType.DATETIME:
            column_type = DateTime
        elif attribute_type == AttributeType.INT_OR_NULL:
            column_type = IntOrNullType
        elif attribute_type == AttributeType.TEXT_OR_NULL:
            column_type = TextOrNullType
        elif attribute_type == AttributeType.FLOAT_OR_NULL:
            column_type = FloatOrNullType
        elif attribute_type == AttributeType.FORM_OR_NULL:
            column_type = FormOrNullType
        elif attribute_type == AttributeType.BOOL_OR_NULL:
            column_type = BoolOrNullType
        elif attribute_type == AttributeType.FILE_OR_NULL:
            column_type = FileOrNullType

        return column_type

    def __repr__(self):
        return "<SchemaMeta>"
