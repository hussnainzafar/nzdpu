"""Migration tools builder."""

import json
from dataclasses import dataclass, field
from datetime import datetime

from .models import (
    WisAttributePromptDataModel,
    WisChoiceDataModel,
    WisColumnDefDataModel,
    WisColumnViewDataModel,
    WisTableDefDataModel,
    WisTableViewDataModel,
)
from .. import settings
from ..schemas.column_def import AttributeType
from ..schemas.create_form import (
    CreateAttribute,
    CreateAttributeView,
    CreateChoice,
    CreateForm,
    CreateFormView,
    CreatePrompt,
)


@dataclass
class FormMigrationDataBuilder:
    data_dir = settings.BASE_DIR
    wis_attribute_prompt: list[WisAttributePromptDataModel] = field(
        default_factory=list
    )
    wis_choice: list[WisChoiceDataModel] = field(default_factory=list)
    wis_column_def: list[WisColumnDefDataModel] = field(default_factory=list)
    wis_column_view: list[WisColumnViewDataModel] = field(default_factory=list)
    wis_table_def: list[WisTableDefDataModel] = field(default_factory=list)
    wis_table_view: list[WisTableViewDataModel] = field(default_factory=list)

    def _build_table_def_row(
        self, spec: CreateForm, form_id: int, heritable: bool
    ) -> int:
        form_id += 1
        self.wis_table_def.append(
            WisTableDefDataModel(
                id=form_id,
                name=spec.name,
                description=spec.description,
                created_on=datetime.now(),
                user_id=spec.user_id,
                heritable=heritable,
            )
        )

        return form_id

    def _build_table_view_row(self, spec: CreateForm, form_id: int) -> None:
        self.wis_table_view.append(
            WisTableViewDataModel(
                id=form_id,
                table_def_id=form_id,
                name=spec.name,
                description=spec.description,
                revision=1,
                active=True,
                created_on=datetime.now(),
                user_id=spec.user_id,
            )
        )

    def _build_column_def(
        self,
        spec: CreateAttribute,
        column_def_id: int,
        user_id: int,
        form_id: int,
        attribute_type_id: int | None,
    ):
        self.wis_column_def.append(
            WisColumnDefDataModel(
                id=column_def_id,
                table_def_id=form_id,
                name=spec.name,
                created_on=datetime.now(),
                user_id=user_id,
                attribute_type=spec.type,
                attribute_type_id=attribute_type_id,
            )
        )

    def _build_column_view(
        self,
        spec: CreateAttribute,
        column_view_id: int,
        user_id: int,
        form_id: int,
    ):
        spec.view
        view_spec = spec.view or CreateAttributeView()
        constraint_value = (
            [cv.model_dump() for cv in view_spec.constraint_value]
            if view_spec.constraint_value
            else []
        )
        constraint_view = (
            view_spec.constraint_view if view_spec.constraint_view else {}
        )
        self.wis_column_view.append(
            WisColumnViewDataModel(
                id=column_view_id,
                column_def_id=column_view_id,
                table_view_id=form_id,
                created_on=datetime.now(),
                user_id=user_id,
                constraint_value=constraint_value,
                constraint_view=constraint_view,
            )
        )

    def _build_prompt(
        self,
        column_def_id: int,
        prompt: CreatePrompt,
        prompt_id: int,
        language_code: str = "en_US",
    ) -> None:
        self.wis_attribute_prompt.append(
            WisAttributePromptDataModel(
                id=prompt_id,
                column_def_id=column_def_id,
                value=prompt.value,
                description=prompt.description,
                language_code=language_code,
            )
        )

    def _build_choice(
        self,
        choice: CreateChoice,
        choice_id: int,
        set_id: int,
        language_code: str = "en_US",
    ):
        self.wis_choice.append(
            WisChoiceDataModel(
                id=choice_id,
                choice_id=choice.choice_id,
                set_id=set_id,
                set_name=choice.set_name,
                value=choice.value,
                order=choice_id,
                description=choice.description,
                language_code=language_code,
            )
        )

    def _build_attribute(
        self,
        spec: CreateAttribute,
        form_id: int,
        user_id: int,
    ):
        sub_form_id = None
        if spec.type == AttributeType.FORM:
            # create sub-form
            assert spec.form
            sub_form_spec = spec.form
            sub_form_spec.user_id = user_id
            sub_form_id = self.build(
                spec=sub_form_spec, heritable=True, form_id=form_id
            )
            form_id += 1
            # form_id = sub_form_id
        if self.wis_column_def:
            column_def_id = self.wis_column_def[-1].id + 1
        else:
            column_def_id = 1
        self._build_column_def(
            spec=spec,
            column_def_id=column_def_id,
            user_id=user_id,
            form_id=form_id,
            attribute_type_id=form_id if sub_form_id else None,
        )
        self._build_column_view(
            spec=spec,
            column_view_id=column_def_id,
            user_id=user_id,
            form_id=form_id,
        )
        if self.wis_attribute_prompt:
            prompt_id = self.wis_attribute_prompt[-1].id + 1
        else:
            prompt_id = 1
        for prompt in spec.prompts:
            self._build_prompt(
                column_def_id=column_def_id, prompt=prompt, prompt_id=prompt_id
            )
            prompt_id += 1
        # single and attribute columns are bound to choices
        # set choice ID (not choice_id) and set_id from last row, or 1
        if not self.wis_choice:
            choice_id, set_id = 1, 1
        else:
            choice_id = self.wis_choice[-1].id + 1
            set_id = self.wis_choice[-1].set_id + 1
        if sub_form_id:
            form_id = sub_form_id
        if spec.type == AttributeType.SINGLE:
            for choice in spec.choices:
                self._build_choice(
                    choice=choice, choice_id=choice_id, set_id=set_id
                )
                choice_id += 1
                # bind column to choices set
            for col in self.wis_column_def:
                if col.id == column_def_id:
                    col.choice_set_id = set_id
        elif spec.type == AttributeType.MULTIPLE:
            # general form data
            sub_form_name: str = f"{spec.name}_form"
            sub_form_description: str = f"Form for {spec.name}"
            # default view
            sub_view_name: str = f"{spec.name}_view"
            sub_view_description: str = f"View for {spec.name}"
            sub_view = CreateFormView(
                name=sub_view_name, description=sub_view_description
            )
            # default attributes for holding
            # choice selection (int) and extra values (text)
            sub_form_attributes: list[CreateAttribute] = [
                CreateAttribute(
                    type=AttributeType.INT, name=f"{spec.name}_int"
                ),
                CreateAttribute(
                    type=AttributeType.TEXT, name=f"{spec.name}_text"
                ),
            ]
            sub_form = CreateForm(
                name=sub_form_name,
                description=sub_form_description,
                user_id=user_id,
                view=sub_view,
                attributes=sub_form_attributes,
            )
            form_id = self.build(
                spec=sub_form, heritable=True, form_id=form_id
            )
            for choice in spec.choices:
                self._build_choice(
                    choice=choice, choice_id=choice_id, set_id=set_id
                )
                choice_id += 1
            for col in self.wis_column_def:
                if col.id == column_def_id:
                    col.choice_set_id = set_id
                    col.attribute_type_id = form_id

        return form_id

    def build(
        self, spec: CreateForm, heritable: bool = False, form_id: int = 0
    ) -> int:
        form_id = self._build_table_def_row(
            spec=spec, form_id=form_id, heritable=heritable
        )
        self._build_table_view_row(spec=spec, form_id=form_id)
        for attribute in spec.attributes:
            form_id = self._build_attribute(
                spec=attribute, form_id=form_id, user_id=spec.user_id
            )

        return form_id

    def save(self):
        migration_data_dir = self.data_dir / "migration_tools/data"
        with open(migration_data_dir / "wis_attribute_prompt.json", "w") as f:
            json.dump(
                [row.model_dump() for row in self.wis_attribute_prompt],
                f,
                default=datetime.isoformat,
                indent=2,
            )
        with open(migration_data_dir / "wis_choice.json", "w") as f:
            json.dump(
                [row.model_dump() for row in self.wis_choice],
                f,
                default=datetime.isoformat,
                indent=2,
            )
        with open(migration_data_dir / "wis_column_def.json", "w") as f:
            json.dump(
                [row.model_dump() for row in self.wis_column_def],
                f,
                default=datetime.isoformat,
                indent=2,
            )
        with open(migration_data_dir / "wis_column_view.json", "w") as f:
            json.dump(
                [row.model_dump() for row in self.wis_column_view],
                f,
                default=datetime.isoformat,
                indent=2,
            )
        with open(migration_data_dir / "wis_table_def.json", "w") as f:
            json.dump(
                [row.model_dump() for row in self.wis_table_def],
                f,
                default=datetime.isoformat,
                indent=2,
            )
        with open(migration_data_dir / "wis_table_view.json", "w") as f:
            json.dump(
                [row.model_dump() for row in self.wis_table_view],
                f,
                default=datetime.isoformat,
                indent=2,
            )
