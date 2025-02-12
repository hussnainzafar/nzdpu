"""Test forms"""

import json

from jsonschema.validators import validate

from app import settings
from app.schemas.create_form import CreateForm
from app.schemas.get_form import GetForm
from app.utils import load_json_schema
from tests.constants import SCHEMA_FILE_NAME


class TestForms:
    """
    Unit tests for forms schema
    """

    data_dir: str = f"{settings.BASE_DIR}/../tests/data"

    def test_form_builder_schema(self):
        """
        Test form builder schema
        """

        # load form specification
        path: str = f"{self.data_dir}/form-create.json"
        with open(path, encoding="utf-8") as f_spec:
            j_spec = json.load(f_spec)

        # validates and builds schema
        form = CreateForm(**j_spec)
        assert form

    def test_form_reader_schema(self):
        """
        Test form reader schema
        """

        # load form specification
        path: str = f"{self.data_dir}/form-get.json"
        with open(path, encoding="utf-8") as f_spec:
            j_spec = json.load(f_spec)

        # validates and builds schema
        form = GetForm(**j_spec)
        assert form

    def test_validate_form_create_schema(self):
        """
        Validates sample form-create specification against the corresponding json-schema
        """

        # load form specification
        path: str = f"{self.data_dir}/form-create.json"
        with open(path, encoding="utf-8") as f_spec:
            j_spec = json.load(f_spec)

        # load json-schema
        (schema, resolver) = load_json_schema("schema-form-create")
        # validate request
        validate(j_spec, schema, resolver=resolver)

    def test_validate_form_get_schema(self):
        """
        Validates sample form-get specification against the corresponding json-schema
        """

        # load form specification
        path: str = f"{self.data_dir}/form-get.json"
        with open(path, encoding="utf-8") as f_spec:
            j_spec = json.load(f_spec)

        # load json-schema
        (schema, resolver) = load_json_schema("schema-form-get")
        # validate request
        validate(j_spec, schema, resolver=resolver)

    def test_validate_nzdpu_general_requirements_schema(self):
        """
        Validates "General Requirements" form specification against the corresponding json-schema
        """

        # load form specification
        path: str = f"{self.data_dir}/nzdpu-general-requirements.json"
        with open(path, encoding="utf-8") as f_spec:
            j_spec = json.load(f_spec)

        # load json-schema
        (schema, resolver) = load_json_schema("schema-form-create")
        # validate request
        validate(j_spec, schema, resolver=resolver)

    def test_validate_nzdpu_scope_1_schema(self):
        """
        Validates "Scope 1" form specification against the corresponding json-schema
        """

        # load form specification
        path: str = f"{self.data_dir}/nzdpu-scope-1.json"
        with open(path, encoding="utf-8") as f_spec:
            j_spec = json.load(f_spec)

        # load json-schema
        (schema, resolver) = load_json_schema("schema-form-create")
        # validate request
        validate(j_spec, schema, resolver=resolver)

    def test_validate_nzdpu_scope_2_schema(self):
        """
        Validates "Scope 2" form specification against the corresponding json-schema
        """

        # load form specification
        path: str = f"{self.data_dir}/nzdpu-scope-2.json"
        with open(path, encoding="utf-8") as f_spec:
            j_spec = json.load(f_spec)

        # load json-schema
        (schema, resolver) = load_json_schema("schema-form-create")
        # validate request
        validate(j_spec, schema, resolver=resolver)

    def test_validate_nzdpu_scope_3_schema(self):
        """
        Validates "Scope 3" form specification against the corresponding json-schema
        """

        # load form specification
        path: str = f"{self.data_dir}/nzdpu-scope-3.json"
        with open(path, encoding="utf-8") as f_spec:
            j_spec = json.load(f_spec)

        # load json-schema
        (schema, resolver) = load_json_schema("schema-form-create")
        # validate request
        validate(j_spec, schema, resolver=resolver)

    def test_validate_nzdpu_full_schema(self):
        """
        Validates full form specification against the corresponding json-schema
        """

        # load form specification
        path: str = f"{self.data_dir}/nzdpu-full.json"
        with open(path, encoding="utf-8") as f_spec:
            j_spec = json.load(f_spec)

        # load json-schema
        (schema, resolver) = load_json_schema("schema-form-create")
        # validate request
        validate(j_spec, schema, resolver=resolver)

    def test_validate_nzdpu_v4_schema(self):
        """
        Validates form specification v.4 against the corresponding json-schema
        """

        # load form specification
        path: str = f"{self.data_dir}/{SCHEMA_FILE_NAME}"
        with open(path, encoding="utf-8") as f_spec:
            j_spec = json.load(f_spec)

        # load json-schema
        (schema, resolver) = load_json_schema("schema-form-create")
        # validate request
        validate(j_spec, schema, resolver=resolver)
