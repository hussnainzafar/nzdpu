import random
import string
from datetime import datetime
from time import time_ns
from typing import Any, Sequence

from fastapi import HTTPException, status
from sqlalchemy import (
    bindparam,
    func,
    insert,
    literal_column,
    select,
    text,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AggregatedObjectView,
    ColumnDef,
    Organization,
    Restatement,
    SubmissionObj,
    TableDef,
)
from app.db.redis import RedisClient
from app.db.types import (
    BoolOrNullType,
    FileOrNullType,
    FloatOrNullType,
    FormOrNullType,
    IntOrNullType,
    NullTypeState,
    PostgresCustomType,
    TextOrNullType,
)
from app.forms.form_meta import FormMeta
from app.loggers import get_nzdpu_logger
from app.schemas.column_def import AttributeType
from app.schemas.enums import SubmissionObjStatusEnum
from app.schemas.restatements import AttributePathsModel, RestatementCreate
from app.schemas.submission import (
    RevisionUpdate,
    SubmissionCreate,
    SubmissionGet,
    SubmissionUpdate,
)
from app.service.core.cache import CoreMemoryCache
from app.service.core.checker import Checker
from app.service.core.converter import Converter
from app.service.core.errors import SubmissionError
from app.service.core.forms import FormValuesGetter
from app.service.core.loaders import FormBatchLoader, SubmissionLoader
from app.service.core.mixins import GetterMixin
from app.service.core.types import RecurseAttributeTypes
from app.service.core.utils import strip_none

logger = get_nzdpu_logger()


def get_required_constraint_value(column: ColumnDef):
    if len(column.views) == 0:
        return None
    view = column.views[0]

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

    if "required" not in set_var:
        return None

    return set_var.get("required")


class SubmissionManager(GetterMixin):
    def __init__(
        self,
        session: AsyncSession,
        core_cache: CoreMemoryCache,
        redis_cache: RedisClient,
    ):
        super().__init__(session, core_cache, redis_cache)

        # save all field names from the submission that are required
        self.required_columns_in_submission = set()
        # save all required field names from the schema
        self.columns_by_name_required_constraint_value: dict[
            str, ColumnDef
        ] = {}

    @classmethod
    def convert_multiple_to_form(
        cls, values: list[int | str], attr_name: str
    ) -> list[dict]:
        return Converter.convert_multiple_to_form(values, attr_name)

    @classmethod
    def convert_form_to_multiple(
        cls, values: list[dict], attr_name: str
    ) -> list[int | str]:
        return Converter.convert_form_to_multiple(values, attr_name)

    async def _generate_submission_name(self, form_name: str) -> str:
        """
        --- This is still on hold for a definitive spec ---
        Generate a unique name for the submission.

        Args:
            form_name (str): The form's name.

        Returns:
            str: The generated unique string.
        """
        # pylint: disable = not-callable
        last_submission_id = await self.session.execute(
            select(func.max(SubmissionObj.id))
        )
        last_submission_id = last_submission_id.scalar()
        if last_submission_id is not None:
            last_submission_id += 1
        else:
            last_submission_id = 0
        # get random character
        r_char = random.choice(string.ascii_uppercase)
        return f"NZDPU-{form_name}-{last_submission_id}-{time_ns()}-{r_char}"

    async def _create_submission_obj(
        self,
        submission: SubmissionCreate,
        name: str,
        submitted_by: int,
        draft_state: SubmissionObjStatusEnum | None = None,
    ) -> SubmissionObj:
        """
        Creates a new submission object

        Args:
            submission (SubmissionCreate): The submission data.
            name (str): The submission object name.
            submitted_by (int): The user ID of the submitting user.
            draft_state (SubmissionObjStatusEnum | None, optional): The
                submission draft state. Defaults to None.

        Returns:
            SubmissionObj: The newly created submission object.
        """
        # Make sure we have consistent data_source across all submission data.
        data_source = submission.data_source or submission.values.get(
            "disclosure_source"
        )
        submission.data_source = data_source
        submission.values["disclosure_source"] = data_source

        lei = submission.values.get("legal_entity_identifier")

        # create the new submission revision
        submission_obj = SubmissionObj(
            table_view_id=submission.table_view_id,
            name=name,
            revision=submission.revision,
            data_source=submission.data_source,
            lei=lei,
            nz_id=submission.nz_id,
            submitted_by=submitted_by,
            permissions_set_id=submission.permissions_set_id,
        )
        if draft_state:
            submission_obj.status = draft_state
        self.session.add(submission_obj)
        await self.session.commit()

        return submission_obj

    async def _get_max_form_type_ids(
        self, form_name: str, columns: list[ColumnDef]
    ) -> int:
        """
        Query the DB for form type IDs and get the next available number.

        Args:
            form_name (str): The name of the form table.
            columns (list[ColumnDef]): The columns definitions for the
                form table.

        Returns:
            int: The next available form ID.
        """

        # Filter columns for those with attribute types FORM or MULTIPLE
        form_type_columns = [
            col.name
            for col in columns
            if col.attribute_type
            in [AttributeType.FORM, AttributeType.MULTIPLE]
        ]

        if not form_type_columns:
            return 1

        # Construct the MAX(GREATEST(...)) statement
        max_expression = func.max(
            func.greatest(*[literal_column(col) for col in form_type_columns])
        )

        form_table = await self.static_cache.get_form_table(form_name)
        # Build the query using SQLAlchemy
        query = select(max_expression).select_from(form_table)

        # Execute the query asynchronously
        max_values = await self.session.scalar(query)

        return int(max_values) + 1 if max_values else 1

    @staticmethod
    def _create_new_row_in_subform(
        submission_id: int,
        row: dict,
        field_name: str,
        field_value: Any,
        form: list,
        heritable: bool,
        value_id: int,
    ) -> dict:
        """
        Creates a new row for sub-forms with multiple rows.

        Args:
            row (dict): The current row.
            field_name (str): The current field in the current row.
            form (list): The global form.
            heritable (bool): Whether the current form is an heritable
                or not.

        Returns:
            dict: The current row, or a new one.
        """
        if field_name in row:
            form.append(row)
            row = {"obj_id": submission_id, field_name: field_value}
            if heritable:
                # keep same form_id of parent form
                row["value_id"] = value_id

        return row

    async def _handle_subforms(
        self,
        submission_id: int,
        row: dict,
        field_name: str,
        form_id: int,
        column: ColumnDef,
        values,
        values_to_insert: list,
        attribute_name: str,
        attribute_type: str,
    ):
        """
        Calls recursion through the structure to insert values in
        sub-forms.

        Args:
            row (dict): The current row.
            field_name (str): The current field of the current row.
            form_id (int): The form ID.
            column (ColumnDef): The column for the current field.
            values (_type_): The value of the current field.
            values_to_insert (list): The values reformatted for
                insertion in the DB.
        """
        # the parent form will use the form_id as value for this field
        row[field_name] = form_id
        table_defs = await self.static_cache.table_defs()
        table_def = table_defs[column.attribute_type_id]
        sub_form_name = table_def.name + "_heritable"
        # and create a new dict for it
        new_sub_form = {sub_form_name: []}
        # recursively calls _get_values_to_insert for each sub-form
        # (and any sub-sub-forms inside the sub-form!)
        latest_form_id = await self._get_values_to_insert(
            submission_id=submission_id,
            new_form=new_sub_form[sub_form_name],
            form_id=form_id,
            values=values,
            values_to_insert=values_to_insert,
            heritable=table_def.heritable,
            attribute_name=attribute_name,
            attribute_type=attribute_type,
        )
        values_to_insert.append(new_sub_form)

        return latest_form_id

    async def _get_values_to_insert(
        self,
        submission_id: int,
        new_form: list,
        form_id: int,
        values: list[dict[str, Any] | str | int] | dict[str, Any],
        values_to_insert: list,
        heritable: bool = False,
        attribute_name: str | None = None,
        attribute_type: str | None = None,
    ):
        """
        Calls recursion through the structure to prepare values
        accordingly and set them in the final insert structure.

        Args:
            new_form (list): The global form.
            form_id (int): The form ID.
            values (list | dict): The values to be inserted.
            values_to_insert (list): The final insert structure.
            heritable (bool, optional): Whether the form is an
                heritable. Defaults to False.
            attribute_name (str | None, optional): The current attribute
                name. Defaults to None.
            attribute_type (str | None, optional): The current attribute
                type. Defaults to None.
        """
        # transform to list to ensure consistency
        if not isinstance(values, list):
            values = [values]
        row = {"obj_id": submission_id}
        if heritable:
            # set value_id for parent form
            row["value_id"] = form_id

        if heritable and attribute_type == AttributeType.MULTIPLE:
            # check format
            if values and not isinstance(values[0], dict):
                assert attribute_name
                # convert values to dictionaries,
                # so that we can treat a multiple like a form
                values = Converter.convert_multiple_to_form(
                    values,
                    attr_name=attribute_name,  # type: ignore
                )

        # for row in new_form:
        for value in values:
            if value is None:  # NOTE: should never enter here
                # empty form
                value = {}

            if not isinstance(value, dict):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        f"{attribute_name}": (
                            f"bad type: expected dictionary, found: {value}."
                        )
                    },
                )

            # iterate through row columns
            for field_name, v in value.items():
                if (
                    field_name
                    in self.columns_by_name_required_constraint_value
                ):
                    self.required_columns_in_submission.add(field_name)

                if field_name in {
                    "id",
                    "obj_id",
                    "value_id",
                } or field_name.endswith("_prompt"):
                    continue
                row = self._create_new_row_in_subform(
                    submission_id=submission_id,
                    row=row,
                    field_name=field_name,
                    field_value=v,
                    form=new_form,
                    heritable=heritable,
                    value_id=row.get("value_id", form_id),
                )
                columns = await self.static_cache.column_defs_by_name()
                column = columns[field_name]
                Checker._validate_constraints(column=column, value=v)
                if column.attribute_type in RecurseAttributeTypes:
                    if v in NullTypeState.values():
                        row[field_name] = v
                        continue
                    latest_form_id = await self._handle_subforms(
                        submission_id=submission_id,
                        row=row,
                        field_name=field_name,
                        form_id=form_id,
                        column=column,
                        values=v,
                        values_to_insert=values_to_insert,
                        attribute_name=column.name,
                        attribute_type=column.attribute_type,
                    )
                    # every time we finish with a sub-form we increment
                    # the latest form id returned by sub-form
                    # form_id += 1
                    form_id = latest_form_id + 1
                else:
                    row[field_name] = v

        new_form.append(row)

        return form_id

    async def _create_insert_data(
        self,
        submission_id: int,
        form_name: str,
        form_id: int,
        values: dict,
    ) -> list[dict[str, Any]]:
        """
        Prepares the structures and data needed to get the values to be
        inserted in the database.

        Args:
            form_name (str): A form name.
            form_id (int): A form ID.
            values (dict | list): The values to be inserted.

        Returns:
            list: The reformatted values ready to be inserted in the DB.
        """
        # store all needed data locally
        values_to_insert = []
        new_form = {form_name: []}
        # then we refactor the data structure
        await self._get_values_to_insert(
            submission_id=submission_id,
            new_form=new_form[form_name],
            values=values,
            values_to_insert=values_to_insert,
            form_id=form_id,
        )
        # and add it to the list
        values_to_insert.append(new_form)

        return values_to_insert

    def get_bind_param_for_null_type_attribute(
        self, k: str, value: Any, composite_type: str
    ):
        value_to_inset = None
        state = None
        # if value is inserted as null
        if value is None:
            value_to_inset = None
            state = NullTypeState.LONG_DASH.value
        elif value in NullTypeState.values():
            value_to_inset = None
            state = value
        else:
            # add parsing for different composite types
            try:
                if (
                    composite_type == PostgresCustomType.INT_OR_NULL
                    or composite_type
                    == PostgresCustomType.FILE_OR_NULL  # because the file value is an id of type int
                ):
                    value_to_inset = int(value)
                elif composite_type == PostgresCustomType.FLOAT_OR_NULL:
                    value_to_inset = float(value)
                elif composite_type == PostgresCustomType.BOOL_OR_NULL:
                    value_to_inset = bool(value)
                else:
                    value_to_inset = value
            except ValueError as exc:
                error_detail = {}
                error_detail[k] = f"Invalid input: {exc}"
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=error_detail,
                ) from exc

        # every bind param should have its own variable naming
        value_var_name = f"value_{k}"
        state_var_name = f"state_{k}"

        params = {}
        params[value_var_name] = value_to_inset
        params[state_var_name] = state

        return (
            text(
                f"ROW(:{value_var_name}, :{state_var_name})::{composite_type}"
            )
            .bindparams(**params)
            .compile(compile_kwargs={"literal_binds": True})
            .statement
        )

    async def _init_column_required_column(self):
        columns_by_name: dict[
            str, ColumnDef
        ] = await self.static_cache.column_defs_by_name()
        columns = columns_by_name.values()

        columns_with_required_constraint_value: list[ColumnDef] = list(
            filter(
                lambda x: get_required_constraint_value(x) is not None, columns
            )
        )

        for column in columns_with_required_constraint_value:
            self.columns_by_name_required_constraint_value[column.name] = (
                column
            )

    async def _verify_required_missing_fields(self):
        for key in self.columns_by_name_required_constraint_value.keys():
            if key in self.required_columns_in_submission:
                # if the field exists in submission then skip the validation
                continue
            else:
                # if the field that must be required does not exist in validation then throw error
                Checker._validate_constraints(
                    column=self.columns_by_name_required_constraint_value[key],
                    value=None,
                )

    async def _insert(self, submission: SubmissionGet) -> None:
        """
        Utility function to insert data in forms and sub-forms.

        Args:
            submission (SubmissionGet): The values to insert.
        """
        # load all needed data
        table_views = await self.static_cache.table_views()
        column_defs = await self.static_cache.column_defs_by_name()
        table_view = table_views[submission.table_view_id]
        table_def: TableDef = table_view.table_def
        form_name: str = table_def.name
        # get max form id for sub-forms
        form_id = await self._get_max_form_type_ids(
            form_name, table_def.columns
        )

        await self._init_column_required_column()
        values_to_insert = await self._create_insert_data(
            submission_id=submission.id,
            form_name=form_name,
            form_id=form_id,
            values=submission.values,
        )
        await self._verify_required_missing_fields()

        row_count = 0
        for table in values_to_insert:
            rows: list[dict[str, Any]]
            for form_name, rows in table.items():
                form_table = await self.static_cache.get_form_table(form_name)
                for row in rows:
                    row_count += 1
                    params = {}
                    for k, v in row.items():
                        if k not in {"obj_id", "value_id"}:
                            attribute_type = column_defs[k].attribute_type
                        else:
                            attribute_type = AttributeType.INT
                        # convert datetime as str to datetime type
                        if (
                            attribute_type == AttributeType.DATETIME
                            and isinstance(v, str)
                        ):
                            if v.endswith("Z"):
                                v = v[:-1]  # remove zulu
                            v = datetime.fromisoformat(v)
                        sql_type = FormMeta.get_column_type(attribute_type)
                        if sql_type is IntOrNullType:
                            params[k] = (
                                self.get_bind_param_for_null_type_attribute(
                                    k, v, PostgresCustomType.INT_OR_NULL
                                )
                            )
                        elif sql_type is TextOrNullType:
                            params[k] = (
                                self.get_bind_param_for_null_type_attribute(
                                    k, v, PostgresCustomType.TEXT_OR_NULL
                                )
                            )
                        elif sql_type is BoolOrNullType:
                            params[k] = (
                                self.get_bind_param_for_null_type_attribute(
                                    k, v, PostgresCustomType.BOOL_OR_NULL
                                )
                            )
                        elif sql_type is FloatOrNullType:
                            params[k] = (
                                self.get_bind_param_for_null_type_attribute(
                                    k, v, PostgresCustomType.FLOAT_OR_NULL
                                )
                            )
                        elif sql_type is FormOrNullType:
                            params[k] = (
                                self.get_bind_param_for_null_type_attribute(
                                    k, v, PostgresCustomType.FORM_OR_NULL
                                )
                            )
                        elif sql_type is FileOrNullType:
                            params[k] = (
                                self.get_bind_param_for_null_type_attribute(
                                    k, v, PostgresCustomType.FILE_OR_NULL
                                )
                            )
                        else:
                            params[k] = bindparam(
                                key=k, value=v, type_=sql_type
                            )  # type: ignore

                    stmt = insert(form_table).values(params)
                    await self.session.execute(stmt)

    async def save_aggregate(
        self,
        obj_id: int,
        submission_data: dict[str, Any],
        commit: bool = False,
        flush: bool = False,
    ) -> None:
        form_loader = FormBatchLoader(
            self.session, self.static_cache, self.redis_cache, obj_id
        )
        form_data = await form_loader.fetch_form_row_data()
        primary_table_def = await form_loader.primary_form_table_def
        form_manager = FormValuesGetter(
            self.static_cache,
            self.redis_cache,
            form_rows=form_data,
            primary_form=primary_table_def,
        )
        submission_values, submission_units = await form_manager.get_values()
        submission_data["values"] = (
            submission_values[0] if submission_values else {}
        )
        submission_data["units"] = (
            submission_units[0] if submission_units else {}
        )
        aggregate = (
            await self.session.scalars(
                select(AggregatedObjectView).where(
                    AggregatedObjectView.obj_id == obj_id
                )
            )
        ).first()

        aggregate_data = SubmissionGet.model_validate(
            submission_data
        ).model_dump(mode="json")

        if not aggregate:
            aggregate = AggregatedObjectView(
                obj_id=obj_id,
                data=aggregate_data,
            )
            self.session.add(aggregate)

        else:
            try:
                aggregate.data = aggregate_data
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={"error": str(e)},
                ) from e

        if flush:
            await self.session.flush()
        if commit:
            await self.session.commit()

    async def update(
        self,
        submission_db: SubmissionGet,
        submission_update: SubmissionUpdate,
    ) -> SubmissionGet:
        """
        Updates the values of an empty submitted submission.

        Args:
            submission_db (Submissionget): The submission object.
            submission_update (SubmissionUpdate): The submission's values.

        Raises:
            HTTPException: If the selected submission is not empty.

        Returns:
            SubmissionObj: The updated submission object.
        """
        if submission_db.values:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"global": SubmissionError.SUBMISSION_NOT_EMPTY},
            )
        submission_db.values = submission_update.values

        await self._insert(submission_db)

        await self.session.commit()

        await self.save_aggregate(
            submission_db.id,
            submission_db.model_dump(mode="json"),
            commit=True,
        )

        return submission_db

    async def check_duplicate_submission(
        self, submission: SubmissionCreate, nz_id: int
    ):
        """
        Used by "Create Submission" API to check if the new submission is a
        duplicate of an existing one.

        Parameters
        ----------
        submission - the submission to check
        session - database session
        user_id - identifier of the currently logged-in user

        Raises
        ------

        HTTPException - if the submission is found to be a duplicate
        """

        reporting_year: int | None = (
            submission.values[FormMeta.f_reporting_year]
            if FormMeta.f_reporting_year in submission.values
            else None
        )

        if reporting_year:
            try:
                f = await self.static_cache.get_form_table()

                query = (
                    select(func.count().label("c"))
                    .select_from(f)
                    .join(
                        SubmissionObj,
                        f.c[FormMeta.f_obj_id] == SubmissionObj.id,
                    )
                    .where(
                        SubmissionObj.nz_id == nz_id,
                        f.c[FormMeta.f_reporting_year] == reporting_year,
                    )
                )
                result = await self.session.execute(query)
                count = result.scalar()
                if count:
                    # found duplicated submission
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail={
                            "submissions": (
                                SubmissionError.SUBMISSION_ALREADY_EXISTS
                            )
                        },
                    )

            except ValueError as value_exc:
                # reporting date not valid
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"submission": SubmissionError.SUBMISSION_NO_DATE},
                ) from value_exc

    async def create(
        self,
        submission: SubmissionCreate,
        table_def: TableDef,
        current_user_id: int,
        name: str = "",
        commit: bool = True,
    ) -> SubmissionObj:
        """
        Creates a new submission, with values if provided (in the
        SubmissionCreate object).

        Args:
            submission (SubmissionCreate): The submission data.
            current_user_id (int): The ID of the current user.
            name (str, optional): The submission's name. Defaults to "".
            commit (bool, optional): Whether to commit the submission to the database

        Returns:
            SubmissionObj: The newly created submission object.
        """
        # load table definition to get form name and use it in submission name
        # create submission object
        # set name
        form_name: str = table_def.name
        if not name:
            # create unique name for submission
            name = await self._generate_submission_name(form_name)
        submission_obj = await self._create_submission_obj(
            submission=submission,
            name=name,
            submitted_by=current_user_id,
            draft_state=SubmissionObjStatusEnum.DRAFT,
        )
        # return empty submission on empty values
        if not submission.values or not set(submission.values.keys()) - {
            "legal_entity_identifier",
            "disclosure_source",
        }:
            submission_obj.user_id = current_user_id
            submission_obj.checked_out = True
            submission_obj.checked_out_on = datetime.now()
            self.session.add(submission_obj)

            return submission_obj

        submission_obj.values = submission.values
        await self._insert(submission=submission_obj)

        # add here to get IDs
        self.session.add(submission_obj)

        if commit:
            await self.session.commit()

        return submission_obj

    def _update_values(
        self, path: AttributePathsModel, values: dict, value: Any
    ) -> dict:
        keys_path = self._get_dict_path(path=path, values=values, keys_path=[])
        ref, key = self._get_nethermost_dict_reference(values, keys_path)
        ref[key] = value

        return values

    async def _save_restatements(
        self,
        obj_id: int,
        group_id: int,
        path: AttributePathsModel,
        restatement: RestatementCreate,
        data_source: int | None = None,
        reporting_datetime: datetime | None = None,
    ) -> Restatement:
        """
        Saves a restatement in the DB.

        Args:
            submission_id (int): The submission ID.
            path (AttributePathsModel): The path object.
            restatement (RestatementCreate): The restatement object.

        Returns:
            Restatement: The stored restatement.
        """
        new_restatement = Restatement(
            obj_id=obj_id,
            group_id=group_id,
            attribute_name=restatement.path,
            attribute_row=path.row_id,
            reason_for_restatement=restatement.reason,
            data_source=data_source,
            reporting_datetime=reporting_datetime,
        )

        return new_restatement

    def update_values_for_restated_columns(
        self, path: AttributePathsModel, values: dict, value: Any
    ) -> dict:
        return self._update_values(path, values, value)


class RevisionManager(SubmissionManager):
    def __init__(
        self,
        session: AsyncSession,
        core_cache: CoreMemoryCache,
        redis_cache: RedisClient,
        rev_history: Sequence[SubmissionObj],
    ):
        super().__init__(session, core_cache, redis_cache)
        self.rev_history = rev_history

    @property
    def last_revision(self):
        return self.rev_history[0]

    @property
    def first_revision(self):
        return self.rev_history[-1]

    async def update(
        self,
        model: RevisionUpdate,
        current_user_id: int,
        create_submission: bool = False,
        submission_status: SubmissionObjStatusEnum = SubmissionObjStatusEnum.PUBLISHED,
    ) -> SubmissionObj:
        """
        Updates the content of the old submission with the newly
        provided values, then inserts a new submission revision to the
        database. It returns the new submission from the database.

        Args:
            current_user_id (int): The ID of the current user.
            create_submission (bool, optional): Whether to create a new
                submission object for the current revision, or update
                an existing one (draft case). Defaults to False.
            submission_status (SubmissionObjStatusEnum, optional): The
                submission's status. Defaults to
                SubmissionObjStatusEnum.PUBLISHED.

        Returns:
            SubmissionObj: _description_
        """

        # check checked out state and user
        if not self.last_revision.checked_out:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "submission_name": SubmissionError.SUBMISSION_CANT_EDIT
                },
            )
        # load data
        table_views = await self.static_cache.table_views()
        table_view = table_views[self.last_revision.table_view_id]
        table_def: TableDef = table_view.table_def
        loader = SubmissionLoader(
            self.session, self.static_cache, self.redis_cache
        )
        submission = await loader.load(self.last_revision.id, db_only=True)
        if not submission.values:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "global": (
                        "Cannot create revision on an empty submission. Use"
                        " update submission API or create a new submission."
                    )
                },
            )

        submission.values = strip_none(submission.values)  # type: ignore
        submission_json = submission.model_dump(mode="json")
        old_values = submission_json["values"]
        restatement_data_source = submission.data_source

        if model.data_source:
            restatement_data_source = model.data_source

        restatement_reporting_datetime = submission.values.get(  # type: ignore
            "reporting_datetime"
        )
        if model.reporting_datetime:
            restatement_reporting_datetime = model.reporting_datetime

        if isinstance(restatement_reporting_datetime, str):
            restatement_reporting_datetime = datetime.fromisoformat(
                restatement_reporting_datetime
            )

        all_restatements = []
        if len(self.rev_history) > 1:
            if not model.group_id:
                stmt = select(Restatement).where(
                    Restatement.group_id == self.first_revision.id
                )
                result = await self.session.scalars(stmt)
                all_restatements = list(result.all())
                first = all_restatements[0]
                if first:
                    model.group_id = first.group_id
                else:
                    detail = {
                        "global": (
                            "Restatements data integrity is corrupted: "
                            "the revision history and restatement history "
                            f"don't match for submission {submission.name}"
                        )
                    }
                    logger.error(
                        "Internal server errror occured:", detail=detail
                    )
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=detail,
                    )
        elif len(self.rev_history) == 1:
            model.group_id = self.first_revision.id

        (
            updated_values,
            restatements,
        ) = await self._update_values_and_save_restatements(
            obj_id=submission.id,
            group_id=model.group_id,
            restatements=model.restatements,
            values=old_values,  # type: ignore
            create_submission=True,
            data_source=restatement_data_source,
            reporting_datetime=restatement_reporting_datetime,
        )

        submission.values = updated_values
        if create_submission:
            new_submission = SubmissionCreate(
                table_view_id=submission.table_view_id,
                revision=submission.revision + 1,
                permissions_set_id=submission.permissions_set_id,
                data_source=submission.data_source,
                status=submission_status,
                values=submission.values,
                nz_id=submission.nz_id,
            )

            # We have data_source in wis_obj and source in nzdpu_form, so we need to have both with same values.
            new_submission.values["disclosure_source"] = submission.data_source

            # create new submission object
            submission = await self.create(
                table_def=table_def,
                submission=new_submission,
                current_user_id=current_user_id,
                name=submission.name,
            )

        for restatement in restatements:
            restatement.obj_id = submission.id
            self.session.add(restatement)

        await self.session.flush(restatements)
        await self.session.commit()

        return submission

    async def get_legal_name_for_revision(
        self,
        lei: str,
    ):
        """
        Get legal name for a given LEI and reporting year
        """

        organization_name = await self.session.scalar(
            select(Organization.legal_name).where(Organization.lei == lei)
        )
        return organization_name

    async def _update_values_and_save_restatements(
        self,
        obj_id: int,
        group_id: int,
        restatements: list[RestatementCreate],
        values: dict,
        create_submission: bool,
        data_source: int | None = None,
        reporting_datetime: datetime | None = None,
    ) -> tuple[dict, list[Restatement]]:
        """
        Given a list of restatements, updates the value of a submission
        and stores restatements in the DB.

        Args:
            submission_id (int): The submission's ID.
            columns (ColumnDefsDataByName): The column definitions from the DB.
            restatements (list[RestatementCreate]): The list of restatements.
            values (dict): The values of the previous submission.

        Returns:
            tuple[dict, list[Restatement]]: The updated values, and the
                stored restatements.
        """
        restatement_history: list[Restatement] = []
        for restatement in restatements:
            path = await self._unpack_restatement_path(
                submission_id=obj_id,
                restatement_path=restatement.path,
            )

            if create_submission is False:
                # If we are not creating a new submission we need to update the old one.
                await self._update_value_in_db(
                    path=path,
                    value=restatement.value,
                )

            values = self._update_values(
                path=path,
                values=values,
                value=restatement.value,
            )

            if not restatement_history:
                restatement_history = []

            restatement = await self._save_restatements(
                obj_id=obj_id,
                group_id=group_id,
                path=path,
                restatement=restatement,
                data_source=data_source,
                reporting_datetime=reporting_datetime,
            )
            restatement_history.append(restatement)

        return values, restatement_history

    async def _update_value_in_db(
        self, path: AttributePathsModel, value: Any
    ) -> None:
        """
        Update the values of a Python dictionary using an AttributePathsModel
        object.

        Args:
            path (AttributePathsModel): The path object.
            value (Any): The value to update.

        Returns:
            None
        """
        # Recursively update sub-paths
        if path.sub_path:
            return await self._update_value_in_db(path.sub_path, value)

        # Determine the form name and whether it is heritable
        if path.form:
            heritable = await self.session.scalar(
                select(TableDef.heritable).where(
                    TableDef.name == path.form + "_form"
                )
            )
            form_name = (
                path.form + "_form_heritable"
                if heritable
                else path.form + "_form"
            )

            # Construct the update statement using SQLAlchemy
            stmt = (
                update(text(form_name))
                .values({path.attribute: value})
                .where(text("id = :row_id"))
                .execution_options(synchronize_session="fetch")
            )

            # Execute the update statement and commit the transaction
            await self.session.execute(stmt, {"row_id": path.row_id})
            await self.session.commit()
