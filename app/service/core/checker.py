"""
Checker class module.

Contains methods concerning validation in submissions.
"""

from app.constraint_validator import ConstraintValidator
from app.db.models import ColumnDef, ColumnView
from app.loggers import get_nzdpu_logger

logger = get_nzdpu_logger()


class Checker:
    @classmethod
    def _validate_constraints(cls, column: ColumnDef, value) -> None:
        """
        Calls validate() method of ConstraintValidator to validate the
        value of a field being inserted.

        Args:
            column (ColumnDef): The ColumnDef for the field.
            value (_type_): The value of the field.
        """
        try:
            column_view: ColumnView = column.views[0]
        except IndexError:
            logger.warning(f"No column views for column '{column.name}'")
        else:
            constraints = column_view.constraint_value
            if constraints:
                constraint_validator = ConstraintValidator(
                    constraints=constraints, value=value, column=column
                )
                constraint_validator.validate()
