from typing import Any

from pydantic import BaseModel

from app.db.models import ColumnView
from app.db.types import PostgresCustomType
from app.dependencies import StaticCache


class FormGroupBy(BaseModel):
    name: str
    group_by: list[str]
    columns: list[
        Any  # it should be ColumnDef, some error that I have not time to fix
    ]


class SchemaService:
    def __init__(self, static_cache: StaticCache):
        self.static_cache = static_cache

    async def _get_all_forms_column_defs(self):
        column_defs = await self.static_cache.column_defs_by_name()
        column_defs_as_list = list(column_defs.values())
        form_column_defs = list(
            filter(
                lambda x: x.attribute_type == "form"
                or x.attribute_type == PostgresCustomType.FORM_OR_NULL.value,
                column_defs_as_list,
            )
        )
        return form_column_defs

    def _get_group_by_attributes_from_constraint_value(
        self, view: ColumnView
    ) -> list[str] | None:
        if not view.constraint_value or (
            view.constraint_value and len(view.constraint_value) == 0
        ):
            return None
        constraint_value = view.constraint_value[0]

        if "actions" not in constraint_value:
            return None
        actions = constraint_value.get("actions")

        if not isinstance(actions, list) or len(actions) == 0:
            return None
        action: dict = actions[0]

        if "set" not in action:
            return None
        set_var: dict = action.get("set")

        if "groupBy" not in set_var:
            return None

        group_by_array = set_var.get("groupBy")

        if not isinstance(group_by_array, list) or len(group_by_array) == 0:
            return None

        return group_by_array

    async def get_group_by_forms_and_attributes(self):
        column_defs_forms = await self._get_all_forms_column_defs()

        table_defs = await self.static_cache.table_defs()

        forms_group_by: list[FormGroupBy] = []

        for column_def_form in column_defs_forms:
            if len(column_def_form.views) == 0:
                continue
            view = column_def_form.views[0]

            group_by_attributes = (
                self._get_group_by_attributes_from_constraint_value(view)
            )

            if group_by_attributes:
                forms_group_by.append(
                    FormGroupBy(
                        name=column_def_form.name,
                        group_by=group_by_attributes,
                        columns=table_defs.get(
                            column_def_form.attribute_type_id
                        ).columns,
                    )
                )

        return forms_group_by
