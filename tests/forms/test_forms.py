import json
import re
from pathlib import Path
from typing import Optional

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings
from app.forms.form_builder import FormBuilder
from app.forms.form_reader import FormReader
from app.schemas.create_form import CreateForm
from app.schemas.get_form import GetForm
from app.schemas.table_view import FormGetFull
from tests.constants import SCHEMA_FILE_NAME
from tests.routers.auth_test import AuthTest

data_dir: Path = settings.BASE_DIR.parent / "tests" / "data"


@pytest.fixture
def schema():
    """
    Fixture for json schema
    Returns
    -------
    schema
    """

    with open(data_dir / SCHEMA_FILE_NAME, encoding="utf-8") as f:
        return json.load(f)


class TestForms(AuthTest):
    @pytest.mark.asyncio
    async def test_create_form(self, schema, session: AsyncSession):
        # validates and builds the schema
        form_spec = CreateForm(**schema)
        # builds the form
        builder = FormBuilder()
        form_id = await builder.go_build(spec=form_spec, session=session)

        assert form_id == 1

    @pytest.mark.asyncio
    async def test_read_form(self, schema, session: AsyncSession):
        # validates and builds the schema
        form_spec = CreateForm(**schema)
        # builds the form
        builder = FormBuilder()
        form_id = await builder.go_build(spec=form_spec, session=session)

        # read the form that we just created
        reader = FormReader(root_id=form_id)
        form_spec: Optional[GetForm | FormGetFull] = await reader.read(session)
        d_spec = form_spec.model_dump(exclude_none=True) if form_spec else {}
        d_spec_str = json.dumps(d_spec, indent=4, default=str)

        # delete created_on in order to be able to compare the objects
        d_spec_str = re.sub('"created_on":.*,', "", d_spec_str)
        # create a dictionary in order to compare them
        d_spec_json = json.loads(d_spec_str)

        forms_responses: Path = (
            settings.BASE_DIR.parent / "tests/forms/responses"
        )

        #  USE ME IF NEED TO REBUILD THE RESPONSE
        with open(
            forms_responses / "get-created-form.json",
            "w",
        ) as file_resp:
            file_resp.write(d_spec_str)

        with open(
            forms_responses / "get-created-form.json", encoding="utf-8"
        ) as f:
            correct_created_from = f.read()
            # delete created_on in order to be able to compare the objects
            correct_created_from = re.sub(
                '"created_on":.*,', "", correct_created_from
            )
            # create a dictionary in order to compare them
            correct_created_from_json = json.loads(correct_created_from)

        assert d_spec_json == correct_created_from_json
