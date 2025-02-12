from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from string import Formatter
from typing import Any

from fastapi import HTTPException, status
from pandas import DataFrame

from app.db.models import ColumnDef, TableDef
from app.db.redis import RedisClient
from app.db.types import NullTypeState
from app.loggers import get_nzdpu_logger
from app.schemas.column_def import AttributeType
from app.schemas.column_view import (
    ColumnConstraintViewModel,
    ColumnConstraintViewRuleEnum,
    TagConstraintViewModel,
)
from app.service.core.cache import CoreMemoryCache
from app.service.core.converter import Converter
from app.service.core.mixins import CacheMixin
from app.service.utils import format_units

ID_FIELDS = {"id", "obj_id", "value_id"}
logger = get_nzdpu_logger()


@dataclass(slots=True)
class BaseForm:
    static_cache: CoreMemoryCache
    form_storage: dict[str, DataFrame]


@dataclass(slots=True)
class Form(BaseForm):
    name: str
    rows: list[FormRow] = field(init=True, default_factory=list)
    value_id: int | None = None
    parent: FormRow | None = None

    def __post_init__(self) -> None:
        self.rows = [
            FormRow(
                parent=self.parent,
                values=row,
                static_cache=self.static_cache,
                form_storage=self.form_storage,
            )
            for row in self.form_storage[self.name]["form_values"]
            if row.get("value_id") == self.value_id
        ]

    async def get_values(
        self, column: ColumnDef | None = None
    ) -> tuple[
        list[dict[str, Any]] | list[int | str],
        list[dict[str, str | None]],
    ]:
        # recurse until there are no more sub-forms
        rows = []
        unit_rows = []
        for form_row in self.rows:
            values: dict[str, Any] = {}
            units: dict[str, list[dict[str, str | None]] | str | None] = {}
            for attr_name in form_row.values:
                value, unit = await form_row.get_values(field=attr_name)
                values[attr_name] = value
                if attr_name not in ID_FIELDS:
                    units[attr_name] = unit
                await form_row.set_tag(field=attr_name, row=values)
            rows.append(values)
            unit_rows.append(units)

        if column and column.attribute_type == AttributeType.MULTIPLE:
            # convert to multiple format
            rows = Converter.convert_form_to_multiple(rows, column.name)
        return rows, unit_rows


@dataclass(slots=True)
class FormRow(BaseForm):
    parent: FormRow | None
    values: dict[str, Any]

    async def get_root_form(
        self,
        field: str,
    ) -> dict:
        """
        Used for getting units from root targets dict when dealing
        with tgt_progress form
        """
        if field.startswith("tgt_"):
            target_category = "abs" if "abs" in field else "int"
            tgt_id = self.values.get(f"tgt_{target_category}_id_progress")
            target_root = self.form_storage[
                f"tgt_{target_category}_dict_form_heritable"
            ]
            filtered_df = target_root[
                target_root["form_values"].apply(
                    lambda x: x.get(f"tgt_{target_category}_id") == tgt_id
                )
            ]
            filtered_data = filtered_df["form_values"].tolist()
            return filtered_data[0] if filtered_data else {}

    async def get_subform(
        self, column: ColumnDef, value: Any
    ) -> tuple[
        list[dict[str, Any]] | list[int | str] | None,
        list[dict[str, str | None]] | None,
    ]:
        if value in NullTypeState.values():
            return value, None

        # get the table definition for the sub-form
        try:
            table_defs = await self.static_cache.table_defs()
            sub_table_def = table_defs[column.attribute_type_id]
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"column.attribute_type_id": "Not found."},
            ) from exc
        form_name = (
            sub_table_def.name + "_heritable"
            if sub_table_def.heritable
            else sub_table_def.name
        )
        form = Form(
            parent=self,
            name=form_name,
            value_id=value,
            static_cache=self.static_cache,
            form_storage=self.form_storage,
        )
        if not form.rows:
            return None, None

        return await form.get_values(column)

    async def get_values(
        self, field: str
    ) -> tuple[Any, list[dict[str, str | None]] | str | None]:
        value = self.values[field]

        if field in ID_FIELDS:
            return value, None

        columns = await self.static_cache.column_defs_by_name()
        column = columns.get(field)
        if not column:
            return None, None

        match column.attribute_type:
            case AttributeType.BOOL:
                value = bool(value) if value is not None else None
            case AttributeType.TEXT:
                value = str(value) if value is not None else None
            case AttributeType.DATETIME:
                value = value if value is not None else None
            case AttributeType.INT:
                value = int(value) if value is not None else None
            case AttributeType.FLOAT:
                value = float(value) if value is not None else None
            case AttributeType.FORM | AttributeType.FORM_OR_NULL:
                return await self.get_subform(column, value)
            case AttributeType.MULTIPLE:
                # compute units differently here: we want only one unit
                # for the whole multiple choice form
                value, _ = await self.get_subform(column, value)
            case _:
                ...
        if field.startswith("tgt_"):
            parent_values = await self.get_root_form(field=field)
        else:
            parent_values = self.parent.values if self.parent else None
        units = await format_units(
            self.values,
            field,
            self.static_cache.session,
            self.static_cache,
            parent_values,
        )
        return value, units

    def _get_other_choice_field(
        self, tag_table_def: TableDef, tag_key: str
    ) -> TagConstraintViewModel:
        """
        Retrieves the other choice field, defined in the contraint view
        of the tag field column.

        Args:
            tag_key (str): The tag field name.

        Returns:
            TagConstraintViewModel | None: The column view of the choice field
                which can be "other".
        """
        # get column view of form column
        return [
            (
                constraint_view
                if col.attribute_type == AttributeType.FORM
                and (
                    constraint_view := TagConstraintViewModel(
                        **col.views[0].constraint_view
                    )
                )
                and constraint_view.item.additional_props.name_attribute_single
                == tag_key
                else TagConstraintViewModel()
            )
            for col in tag_table_def.columns
        ][0]

    def _get_tag_key(self, prompt: str) -> str | None:
        """
        Get the tag key from the prompt.

        Args:
            prompt (str): The prompt.
            row (dict): The current examined row.

        Returns:
            str | None: The tag key if present, None otherwise.
        """
        # NOTE: we are assuming only one single tag per prompt
        # modify here should multiple tags per prompt become a thing
        tag_key = [p[1] for p in Formatter().parse(prompt)][0]

        return tag_key

    def _get_unit_keys(
        self, units: str
    ) -> list[tuple[str, str | None, str | None, str | None]]:
        unit_keys = list(Formatter().parse(units))
        return unit_keys

    def _get_tag_show_rule(
        self, field_constraint_view: ColumnConstraintViewModel, row: dict
    ) -> bool:
        show = True
        rule_effect = field_constraint_view.rule.effect
        show_rule = rule_effect == ColumnConstraintViewRuleEnum.SHOW
        rule_name = field_constraint_view.rule.conditions[0].name
        rule_const = field_constraint_view.rule.conditions[0].schema_.const
        if rule_name in row:
            show = not (show_rule ^ row[rule_name] == rule_const)

        return show

    def _crawl_form_parents(self, tag_key: str | None):
        if tag_key is None:
            return tag_key
        parent = self.parent
        while parent is not None:
            if tag_key in parent.values:
                return parent.values[tag_key]
            parent = parent.parent

    async def set_tag(self, field: str, row: dict) -> dict:
        column_defs = await self.static_cache.column_defs_by_name()

        # field not a column: return unchanged row
        if field not in column_defs:
            return row

        # get column for field
        field_column = column_defs[field]

        # field has no prompt: return unchanged row
        if not field_column.prompts:
            return row

        # get prompt and tag key from prompt
        field_prompt = field_column.prompts[0]
        tag_key = self._get_tag_key(field_prompt.value)

        # prompt has no tag: return unchanged row
        if not tag_key:
            row[f"{field}_prompt"] = field_prompt.value
            return row
        if tag_key in row:
            tag_value = row[tag_key]
        else:
            tag_value = self._crawl_form_parents(tag_key=tag_key)
        if not tag_value:
            logger.debug(f"No tag found for {field=} and {tag_key=}")
            return row

        # get column views for tag and current field
        # retrieve table definition to get form column
        tag_table_def = column_defs[tag_key].table_def
        tag_constraint_view = self._get_other_choice_field(
            tag_table_def, tag_key
        )
        field_constraint_view = ColumnConstraintViewModel(
            **field_column.views[0].constraint_view
        )
        # get the choice ID value which defines an "other" choice
        other_choice_id = (
            tag_constraint_view.item.additional_props.other_choice_id
        )

        # get rule to show prompt
        show = self._get_tag_show_rule(field_constraint_view, row)

        # get choice id from tag field (not current field)
        choices = column_defs[tag_key].choices
        choice = [c for c in choices if c.choice_id == tag_value][0]
        # if show_other_rule:
        mapping = {}
        # initialize to "Other"
        mapping[tag_key] = "other"
        #  change to actual value if not an "Other" field
        if choice.id != other_choice_id:
            mapping[tag_key] = choice.value
        # add prompt field to dict
        if show:
            row[f"{field}_prompt"] = field_prompt.value.format(**mapping)

        return row

    def __repr__(self):
        values = self.values
        return f"FormRow <{values=}>"


class FormValuesGetter(CacheMixin):
    def __init__(
        self,
        core_cache: CoreMemoryCache,
        redis_cache: RedisClient,
        form_rows: dict[str, list[dict]],
        primary_form: TableDef,
    ):
        super().__init__(core_cache, redis_cache)
        self.form_rows = form_rows
        self.primary_form = primary_form

    @cached_property
    def storage(self) -> dict[str, DataFrame]:
        storage = {}
        for table_name in self.form_rows.keys():
            df = DataFrame.from_dict(
                {
                    "form_values": self.form_rows[table_name],
                },
                orient="index",
            )
            storage[table_name] = df.transpose()
        return storage

    async def get_values(
        self,
    ) -> tuple[list, list]:
        form = Form(
            static_cache=self.static_cache,
            name=self.primary_form.name,
            form_storage=self.storage,
        )
        values, units = await form.get_values()
        return values, units
