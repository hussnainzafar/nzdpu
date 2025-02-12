"""Test routers utility functions"""

from app.service.core.managers import SubmissionManager

# pylint: disable = no-member


class TestRouterUtils:
    """
    Unit tests for utility functions
    """

    def test_convert_multiple_to_form(self):
        """
        GIVEN a submission on a "multiple" attribute
        WHEN  is it converted to the "form" attribute format
        THEN check the conversion is correct
        """

        attr_name: str = "methodology_used"
        attr_int_name: str = f"{attr_name}_int"
        attr_str_name: str = f"{attr_name}_text"
        sub_multiple: list[int | str] = [
            101,
            "choice1",
            103,
            "choice2",
            "choice3",
        ]
        sub_form: list[dict] = SubmissionManager.convert_multiple_to_form(
            values=sub_multiple, attr_name=attr_name
        )

        assert len(sub_form) == len(sub_multiple)
        assert all(
            attr_int_name in sub_form_item for sub_form_item in sub_form
        )
        assert all(
            attr_str_name in sub_form_item for sub_form_item in sub_form
        )
        assert all(
            sub_form[i][attr_int_name] == sub_multiple[i] for i in [0, 2]
        )
        assert all(
            sub_form[i][attr_str_name] == sub_multiple[i] for i in [1, 3, 4]
        )

    def test_convert_form_to_multiple(self):
        """
        GIVEN a submission read from a sub-form table of a "multiple" attribute
        WHEN  is it converted to the "multiple" attribute format
        THEN check the conversion is correct
        """

        attr_name: str = "methodology_used"
        attr_int_name: str = f"{attr_name}_int"
        attr_str_name: str = f"{attr_name}_text"
        sub_form: list[dict] = [
            {"methodology_used_int": 101, "methodology_used_text": ""},
            {"methodology_used_int": -1, "methodology_used_text": "choice1"},
            {"methodology_used_int": 103, "methodology_used_text": ""},
            {"methodology_used_int": -1, "methodology_used_text": "choice2"},
            {"methodology_used_int": -1, "methodology_used_text": "choice3"},
        ]
        sub_multiple: list[int | str] = (
            SubmissionManager.convert_form_to_multiple(
                values=sub_form, attr_name=attr_name
            )
        )

        assert len(sub_multiple) == len(sub_form)
        assert all(
            sub_multiple[i] == sub_form[i][attr_int_name] for i in [0, 2]
        )
        assert all(
            sub_multiple[i] == sub_form[i][attr_str_name] for i in [1, 3, 4]
        )
