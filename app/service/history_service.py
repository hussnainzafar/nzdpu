from app.db.models import ColumnView
from app.db.types import NullTypeState
from app.service.schema_service import FormGroupBy


class HistoryService:
    def _create_utility_variables(
        self, reversed_history: list[dict], form_name: str
    ):
        matrix: list[dict] = []
        # dictionary with all reporting years available initialization with empty arrays
        form_data_by_reporting_year: dict[int, list] = {}

        all_empty = True

        # create a matrix with the forms data
        for i in range(0, len(reversed_history)):
            item = reversed_history[i]
            item_form_data = item.get("submission").values.get(form_name)
            reporting_year = item.get("reporting_year")
            if isinstance(item_form_data, list):
                matrix.append(
                    {"reporting_year": reporting_year, "data": item_form_data}
                )
                all_empty = False

            form_data_by_reporting_year[reporting_year] = []

        return (matrix, form_data_by_reporting_year, all_empty)

    def _get_empty_null_type_obj(self, form_group_by: FormGroupBy):
        item: dict = {}
        columns = [x.name for x in form_group_by.columns]
        for key in columns:
            item[key] = NullTypeState.LONG_DASH.value
        return item

    def _format_primary_key(
        self, form_group_by: FormGroupBy, item: dict
    ) -> str | None:
        key = ""
        for property in form_group_by.group_by:
            data = (
                item.get(property)
                if item.get(property) not in NullTypeState.values()
                else None
            )
            key = f"{key}{'' if key == '' or data is None else '|'}{data if data  else ''}"

        if key == "":
            return None

        return key

    def _get_grouped_form_items_by_primary_keys(
        self,
        matrix: list[dict],
        form_group_by: FormGroupBy,
        column_length: int,
    ):
        # group reporting years with data items by primary keys
        primary_key_data_year_dict: dict[str, list[dict]] = {}
        for i in range(0, column_length):
            data = matrix[i].get("data")
            for j in range(0, len(data)):
                reporting_year = matrix[i].get("reporting_year")
                item = data[j]
                key = self._format_primary_key(form_group_by, item)
                if key is None:
                    continue

                data_with_year = {
                    "reporting_year": reporting_year,
                    "data": item,
                }
                if key not in primary_key_data_year_dict:
                    primary_key_data_year_dict[key] = [data_with_year]
                else:
                    found_item = next(
                        (
                            x
                            for x in primary_key_data_year_dict[key]
                            if x.get("reporting_year") == reporting_year
                        ),
                        None,
                    )
                    # fix corner case in case we have duplicates data for the same years
                    if not found_item:
                        primary_key_data_year_dict[key].append(data_with_year)

        return primary_key_data_year_dict

    def _get_unit_to_compute(self, column_view: ColumnView, values: dict):
        if not isinstance(column_view.constraint_value, list):
            return None
        if len(column_view.constraint_value) == 0:
            return None

        constraint = column_view.constraint_value[0]

        try:
            unit = constraint["actions"][0]["set"]["units"]

            if unit.startswith("{") and unit.endswith("}"):
                v_unit_key = unit.strip("{}")
                # check if field is not in form values and use parent values
                unit_computed = values.get(v_unit_key)

                return unit_computed

            return None
        except Exception:
            return None

    def _create_unit(self, form_group_by: FormGroupBy, values: dict) -> dict:
        unit: dict = {}

        for column in form_group_by.columns:
            key = column.name
            view = column.views[0]
            constraint_value_unit = self._get_unit_to_compute(view, values)
            if "units" not in key:
                unit[key] = constraint_value_unit

        return unit

    def _complete_group_data_by_years(
        self,
        form_items: list[dict],
        form_data_by_reporting_year: dict[int, list],
        form_group_by: FormGroupBy,
    ) -> list[dict]:
        """
        Returns a list of computed units with the same length as the grouped data
        """
        years = form_data_by_reporting_year.keys()
        units: list[dict] = []

        for form_item in form_items:
            for year in years:
                data_array = form_item.get("data_array")
                item_found = next(
                    (x for x in data_array if x.get("reporting_year") == year),
                    None,
                )
                if item_found:
                    unit = self._create_unit(
                        form_group_by, item_found.get("data")
                    )
                    units.append(unit)

                    form_data_by_reporting_year[year].append(
                        item_found.get("data")
                    )
                else:
                    # if we do not have any items, complete the array with long dashes for all attributes of the sub form
                    form_data_by_reporting_year[year].append(
                        self._get_empty_null_type_obj(form_group_by)
                    )

        return units

    def _group_data_by_year(
        self,
        matrix: list[dict],
        form_data_by_reporting_year: dict[int, list],
        form_group_by: FormGroupBy,
    ) -> list[dict]:
        """
        Returns a list of computed units with the same length as the grouped data
        """
        column_length = len(matrix)

        primary_key_data_year_dict = (
            self._get_grouped_form_items_by_primary_keys(
                matrix=matrix,
                form_group_by=form_group_by,
                column_length=column_length,
            )
        )

        # transform grouped items by primary keys in an array
        form_items: list[dict] = []
        for key, data_array in primary_key_data_year_dict.items():
            form_items.append(
                {
                    "key": key,
                    "data_array": data_array,
                }
            )

        def sort_func(x):
            years = [x.get("reporting_year") for x in x.get("data_array")]
            # we add minus for number criteria to sort the desc order and keep sorting in asc for key
            return (-max(years), -len(years), x.get("key"))

        # sort the grouped items to meet client criteria
        sorted_form_items = sorted(
            form_items,
            key=sort_func,
        )

        return self._complete_group_data_by_years(
            form_group_by=form_group_by,
            form_data_by_reporting_year=form_data_by_reporting_year,
            form_items=sorted_form_items,
        )

    def _replace_values_with_grouped_ones_in_history(
        self,
        history: list[dict],
        form_group_by: FormGroupBy,
        form_data_by_reporting_year: dict[int, list],
        units: list[dict],
    ):
        for item in history:
            submission_values = item.get("submission").values
            submission_units = item.get("submission").units
            # replace sorted and grouped items in the submission
            submission_values[form_group_by.name] = (
                form_data_by_reporting_year[item.get("reporting_year")]
            )
            submission_units[form_group_by.name] = units

    def group_form_items(
        self, forms_group_by: list[FormGroupBy], history: list[dict]
    ):
        if len(history) == 0:
            return history

        reversed_history = history[::-1]

        for form_group_by in forms_group_by:
            (matrix, form_data_by_reporting_year, all_empty) = (
                self._create_utility_variables(
                    reversed_history, form_group_by.name
                )
            )

            # if we do not have any data for the grouping, we just skip the grouping
            if all_empty:
                continue

            units = self._group_data_by_year(
                matrix=matrix,
                form_data_by_reporting_year=form_data_by_reporting_year,
                form_group_by=form_group_by,
            )

            self._replace_values_with_grouped_ones_in_history(
                history=history,
                form_group_by=form_group_by,
                form_data_by_reporting_year=form_data_by_reporting_year,
                units=units,
            )
