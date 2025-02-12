from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

import typer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import DBManager
from app.db.models import ColumnDef
from app.schemas.column_def import AttributeType

app = typer.Typer()


@dataclass
class Error:
    name: str
    messages: list[str]
    errors: Optional[list[Error]] = None


def validate_attribute(attribute: dict) -> list[str]:
    errors: list[str] = []

    attr_type = attribute.get("type")
    if not attr_type:
        errors.append("property 'type' is not present")

    attribute_types = [e.value for e in AttributeType]
    if attr_type not in attribute_types:
        errors.append(
            f"property  'type': {attr_type} is not of any of the supported attribute types: {attribute_types}"
        )

    prompts = attribute.get("prompts")
    if not prompts:
        errors.append("property 'prompts' is not present")

    if type(prompts) is not list:
        errors.append("property 'prompts' is not an array")

    for i in range(0, len(prompts)):
        prompt = prompts[i]
        if not prompt.get("value"):
            errors.append(
                f"item of property 'prompts' at index {i} is missing 'value' property"
            )

    if attr_type == AttributeType.SINGLE:
        choices = attribute.get("choices")
        if not choices:
            errors.append(
                "attribute of type single requires to have property 'choices' present"
            )
        if type(choices) is not list:
            errors.append(
                "attribute of type single requires to have property 'choices' as an array"
            )

    return errors


def get_attribute_name_error_message(attribute_name: str) -> str | None:
    is_matched = re.match("^[a-z0-9_]*$", attribute_name)
    if not is_matched:
        return f"attribute name {attribute_name} is not in correct format, it should contain only lowercase letters, underscores and numbers"

    return None


async def validate_attributes(
    attributes: list[dict],
    session: AsyncSession,
    attributes_names: Dict[str, bool],
) -> list[Error]:
    errors: list[Error] = []
    for i in range(0, len(attributes)):
        attribute = attributes[i]
        attribute_name = attribute.get("name")
        form = attribute.get("form")
        error: Error | None = Error(
            name=f"attribute {attribute_name}", messages=[]
        )
        error.messages = validate_attribute(attribute)

        if not attribute_name:
            error.name = f"attribute at index {i}"
            error.messages.append("'name' is not present")
        else:
            error_attribute_name = get_attribute_name_error_message(
                attribute_name
            )
            if error_attribute_name is not None:
                error.messages.append(error_attribute_name)

        if attributes_names.get(attribute_name):
            error.messages.append(
                f"This name '{attribute_name}' is already used in the schema, it must be unique."
            )

        if attribute_name:
            attributes_names[attribute_name] = True

        if form is None and attribute_name:
            query_res = await session.execute(
                select(ColumnDef.name).where(ColumnDef.name == attribute_name)
            )
            res = query_res.scalar_one_or_none()
            if res:
                error.messages.append(
                    f"attribute name {attribute_name} already exists in the database, please edit the name"
                )

        if form:
            form_errors = await validate_schema(
                form, i, session, attributes_names
            )

            if len(form_errors) > 0:
                error.name = f"{error.name} of type form"
                error.errors = form_errors

        if len(error.messages) > 0 or (error.errors and len(error.errors) > 0):
            errors.append(error)

    return errors


async def validate_schema(
    json_spec: Any,
    index: int,
    session: AsyncSession,
    attributes_names: Dict[str, bool],
) -> list[Error]:
    errors: list[Error] = []

    name = json_spec.get("name")
    if attributes_names.get(name):
        errors.append(
            Error(
                name=name,
                messages=[
                    f"This name '{name}' is already used in the schema, it must be unique."
                ],
            )
        )

    if name is None:
        errors.append(
            Error(
                name=(
                    "root form"
                    if index == 0
                    else f"attribute at index {index}"
                ),
                messages=["Property 'name' is missing from root form."],
            )
        )
    else:
        attributes_names[name] = True

    attributes = json_spec.get("attributes")
    if attributes is None:
        errors.append(
            Error(
                name=name,
                messages=["Property 'attributes' is missing from root form."],
            )
        )

    if type(attributes) is not list:
        errors.append(
            Error(
                name=name,
                messages=["Property 'attributes' must a list."],
            )
        )

    attributes_errors = await validate_attributes(
        attributes, session, attributes_names
    )

    errors.extend(attributes_errors)

    return errors


def print_errors(errors: list[Error], indent: int = 2):
    for error in errors:
        indent_space = [" " for _ in range(0, indent - 2)]
        indent_str = "".join(indent_space)
        print(f"{indent_str}{error.name}:")
        for error_str in error.messages:
            indent_space = [" " for _ in range(0, indent)]
            indent_str = "".join(indent_space)
            print(f"{indent_str}-", error_str)

        if error.errors:
            print_errors(error.errors, indent + 2)
            print(" ")
            print(" ")


async def handle_schema_validation(j_spec: Any):
    db_manager = DBManager()
    attributes_names: Dict[str, bool] = {}
    async with db_manager.get_session() as session:
        errors = await validate_schema(j_spec, 0, session, attributes_names)
        if len(errors) > 0:
            print("------------------------------------------------")
            print("The schema is invalid with the following errors:")

            print_errors(errors)
            return

    print("Schema is valid!")


@app.command()
def schema_verifier(path: str):
    """Runs validation on a schema json file to see if the schema is valid and can be created in the database

    Args:
        path (str): path to the json file
    """
    with open(path, encoding="utf-8") as f_spec:
        try:
            j_spec = json.load(f_spec)
        except json.JSONDecodeError:
            print("Invalid schema: json is not valid")
            return
    asyncio.run(handle_schema_validation(j_spec))


if __name__ == "__main__":
    app()
