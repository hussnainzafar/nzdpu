"""
Module holding a ConstraintValidator class.
"""

import base64
import mimetypes
import re
from datetime import datetime, timezone
from typing import Any

import magic
from fastapi import HTTPException

from app.db.models import ColumnDef
from app.schemas.column_def import AttributeType


class ConstraintValidationException(Exception):
    """
    Exception for constraints validation errors.
    """

    def __init__(
        self,
        message: str,
        column_name: str,
        condition: dict,
        action: dict,
        value: Any,
    ):
        """
        Inits the instance of this class.
        """
        self.message = message
        self.column_name = column_name
        self.condition = condition
        self.action = action
        self.value = value


class ConstraintValidator:
    """
    Class which performs checks on values according to constraints.
    """

    def __init__(self, constraints, value, column: ColumnDef):
        """
        Init this class.
        """
        self.constraints = constraints
        self.value = value
        self.column: ColumnDef = column

    def validate(self):
        """
        Begin validation.
        """
        for constraint in self.constraints:
            conditions = constraint["conditions"]
            if conditions:
                self._validate_conditions(conditions)
            actions = constraint["actions"]
            for action in actions:
                self._check_is_valid(action)

    def _get_datetime_from_custom_tag(self, constraint_value) -> str:
        """
        Get datetime constraint value from custom tags.
        """
        new_value = constraint_value
        if new_value == "{currentDate}":
            new_value = datetime.now().isoformat() + "Z"

        return new_value

    def _get_min_max_date(
        self, field: str, action_set: dict
    ) -> datetime | None:
        """
        Get min or max date constraints if any.
        """
        constraint = action_set.get(field)
        if constraint is None:
            return constraint
        # get date object from custom tags
        constraint = self._get_datetime_from_custom_tag(constraint)
        constraint = datetime.fromisoformat(constraint)

        return constraint

    def _get_format_date(self, action_set: dict) -> str | None:
        """
        Retrieves the format contraint from the datetime constraint
        value, if any.
        """
        return action_set.get("format")

    def _check_datetime_valid(
        self,
        dmin: datetime | None,
        dmax: datetime | None,
        dform: str | None,
        action: dict,
    ) -> None:
        """
        Checks that the datetime field adheres to constraints.
        """
        is_valid = True
        date_value = self.value
        # check format
        if dform:
            try:
                date_value = datetime.strptime(date_value, dform)
            except ValueError:
                self._raise_error(action, None)
        else:  # if we don't have a format try isoformat
            try:
                date_value = datetime.fromisoformat(self.value)
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail={
                        str(self.column.name): (
                            f"datetime {date_value} is not a valid"
                            " isoformat string"
                        )
                    },
                ) from exc
            if not date_value.tzinfo:
                # make date value timezone aware
                date_value = date_value.replace(tzinfo=timezone.utc)
        # check min date
        if dmin is not None:
            is_valid = is_valid and dmin <= date_value
        # check max date
        if dmax is not None:
            is_valid = is_valid and date_value <= dmax
        # raise custom exception if not is_valid
        if not is_valid:
            self._raise_error(action, None)

    def _validate_datetime(self, action: dict) -> None:
        """
        Validates datetime against constraints.
        """
        action_set = action["set"]
        # get "min" value
        min_value = self._get_min_max_date("min", action_set)
        max_value = self._get_min_max_date("max", action_set)
        format_value = self._get_format_date(action_set)
        self._check_datetime_valid(min_value, max_value, format_value, action)

    def _validate_number(self, action: dict) -> None:
        """
        Validates int and float types against constraints.
        """
        action_set = action["set"]
        min_value = action_set.get("min")
        max_value = action_set.get("max")

        valid = True
        if self.value is None:
            return
        if not isinstance(self.value, int) and not isinstance(
            self.value, float
        ):
            raise HTTPException(
                status_code=422,
                detail={
                    str(self.column.name): (
                        f"Invalid data type {type(self.value).__name__} in"
                        f" {self.column.name} for comparison."
                        " Must be an number."
                    )
                },
            )
        # check constraints
        if min_value is not None:
            valid = valid and min_value <= self.value
        if max_value is not None:
            valid = valid and self.value <= max_value
        # raise custom exception if not valid
        if not valid:
            self._raise_error(action, None)

    def _validate_text(self, action: dict) -> None:
        """
        Validates text against constraints.
        """
        action_set = action["set"]
        min_value = action_set.get("min")
        max_value = action_set.get("max")
        format_value = action_set.get("format")
        is_valid = True
        if self.value is None:
            return
        if not isinstance(self.value, str):
            raise HTTPException(
                status_code=422,
                detail={
                    str(self.column.name): (
                        f"Invalid data type {type(self.value).__name__}"
                        f" in {self.column.name} for comparison."
                        " Must be a string"
                    )
                },
            )
        # get length of string as value to check
        value_length = len(self.value)
        # check constraints
        if format_value is not None:
            pattern = re.compile(format_value)
            is_valid = is_valid and pattern.match(self.value) is not None
        if min_value is not None:
            is_valid = is_valid and min_value <= value_length
        if max_value is not None:
            is_valid = is_valid and value_length <= max_value
        # raise custom exception if not is_valid
        if not is_valid:
            self._raise_error(action, None)

    def _validate_conditions(self, conditions: list) -> None:
        """
        Validates int and float types against constraints.
        """
        condition_list = []
        for condition in conditions:
            condition_set = condition["set"]
            key, value = self._find_comparison_condition(condition_set)
            valid = True
            # check constraints
            if key == "lt":
                valid = valid and value > self.value
            elif key == "le":
                valid = valid and value >= self.value
            elif key == "eq":
                valid = valid and value == self.value
            elif key == "ge":
                valid = valid and value <= self.value
            elif key == "gt":
                valid = valid and value < self.value
            condition_list.append(valid)
        # raise custom exception if not valid
        if True not in condition_list:
            self._raise_error(None, conditions)

    def _validate_file(self, action: dict) -> None:
        """
        Validates file size and mime type against constraints.
        """
        action_set = action["set"]
        action_accept = action_set.get("accept")
        max_value = action_set.get("max")
        extension = action_accept[0].get("extension")
        mime_type = action_accept[0].get("mime_type")
        base64str = self.value

        # check file size
        length = len(base64str)
        # Determine the number of padding characters at the end of the base64 string
        padding = base64str.count("=")
        # Calculate the size in bytes
        size_bytes = (length * 3 // 4) - padding
        size_kilobytes = size_bytes / 1024
        if size_kilobytes > max_value:
            self._raise_error(None, action)

        # mime type check
        decoded = base64.b64decode(base64str)
        # Initialize magic library
        mime = magic.Magic()
        # Get the MIME type of the binary data
        mimetype = mime.from_buffer(decoded)
        # Set the desired MIME type if "PDF" is present, else use the detected MIME type
        mimetype = "application/pdf" if "PDF" in mimetype.upper() else mimetype
        if mimetype != mime_type:
            self._raise_error(None, action)

        # extension check
        _extension = mimetypes.guess_extension(mimetype)
        if _extension[1:] != extension:
            self._raise_error(None, action)

    def _validate_required(self, action):
        action_set = action["set"]
        required = action_set.get("required")

        is_valid = True

        if required is not None:
            if required is False:
                is_valid = True
            elif required is True and self.value:
                is_valid = True
            else:
                is_valid = False

        if not is_valid:
            self._raise_error(action, None)

    def _raise_error(self, action, condition):
        """
        Utility function which raises a ConstraintValidationException.
        """
        raise ConstraintValidationException(
            message=(
                f"Value for {self.column.name} does not fulfill constraints."
            ),
            column_name=self.column.name,  # type: ignore
            value=self.value,
            condition=condition,
            action=action,
        )

    def _check_is_valid(self, action) -> None:
        """
        Performs checks on values according to defined constraints.

        Args:
            action (_type_): The action, holding the constraints.

        Raises:
            ConstraintValidationException: A custom exception for
                constarints validation errors.
        """
        self._validate_required(action)
        attribute_type = self.column.attribute_type
        if attribute_type == AttributeType.DATETIME:
            self._validate_datetime(action)
        elif attribute_type in [AttributeType.INT, AttributeType.FLOAT]:
            self._validate_number(action)
        elif attribute_type == AttributeType.TEXT:
            self._validate_text(action)
        elif attribute_type == AttributeType.FILE:
            self._validate_file(action)

    def _find_comparison_condition(self, condition):
        """
        Performs extracting operators from constraints.

        Args:
            condition (_type_): The condition, holding the constraints.
        Return:
             { "eq": 1 }
        """
        if isinstance(condition, dict):
            for key, value in condition.items():
                if key in ["lt", "le", "eq", "ge", "gt"]:
                    return {key: value}
                result = self._find_comparison_condition(value)
                if result is not None:
                    key_res = list(result.keys())[0]
                    val_res = result[list(result.keys())[0]]
                    return key_res, val_res
        elif isinstance(condition, list):
            for item in condition:
                result = self._find_comparison_condition(item)
                if result is not None:
                    key_res = list(result.keys())[0]
                    val_res = result[list(result.keys())[0]]
                    return key_res, val_res

        return None, None
