"""
Converter class module.

Contains methods concerning conversion in submissions.
"""


class Converter:
    @classmethod
    def convert_multiple_to_form(
        cls, values: list[int | str], attr_name: str
    ) -> list[dict]:
        """ "
        Convert a submission for a "multiple" attribute to the "form"
        attribute format, for insertion in the heritable tables of the
        original "multiple" attribute
        Parameters
        ----------
        values - values to transform
        attr_name - name of the "multiple" attribute
        Returns
        -------
        the transformed list
        """

        form_values: list[dict] = []
        attr_int_name: str = f"{attr_name}_int"
        attr_str_name: str = f"{attr_name}_text"
        for value in values:
            if isinstance(value, int):
                form_values.append({attr_int_name: value, attr_str_name: ""})
            elif value:
                form_values.append(
                    {attr_int_name: -1, attr_str_name: str(value)}
                )

        return form_values

    @classmethod
    def convert_form_to_multiple(
        cls, values: list[dict], attr_name: str
    ) -> list[int | str]:
        """ "
        Convert a submission read from the sub-form table of a "multiple"
        attribute to the "multiple" attribute format,
        for inclusion in the response body of an API call
        Parameters
        ----------
        values - values to transform
        attr_name - name of the "multiple" attribute
        Returns
        -------
        the transformed list
        """

        multiple_values: list[int | str] = []
        attr_int_name: str = f"{attr_name}_int"
        attr_str_name: str = f"{attr_name}_text"
        for value in values:
            assert isinstance(value, dict), attr_name
            for field_name, field_value in value.items():
                if field_name == attr_int_name:
                    if field_value is not None and int(field_value) != -1:
                        multiple_values.append(int(field_value))
                elif field_name == attr_str_name:
                    if field_value:
                        multiple_values.append(str(field_value))
                elif field_name in ["id", "obj_id", "value_id", "prompt"]:
                    continue
                else:
                    # unexpected field name
                    raise ValueError(f"unexpected field name: {field_name}")

        return multiple_values
