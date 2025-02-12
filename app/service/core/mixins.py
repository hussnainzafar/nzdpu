from typing import Any

import orjson
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis import RedisClient
from app.schemas.restatements import AttributePathsModel
from app.service.core.cache import CoreMemoryCache
from app.utils import convert_keys_to_str


class CacheMixin:
    def __init__(
        self,
        core_cache: CoreMemoryCache,
        redis_cache: RedisClient,
        *args,
        **kwargs,
    ):
        self.static_cache = core_cache
        self.redis_cache = redis_cache
        super().__init__(*args, **kwargs)


class SessionMixin:
    def __init__(self, session: AsyncSession, *args, **kwargs):
        self.session = session
        super().__init__(*args, **kwargs)


class GetterMixin(CacheMixin, SessionMixin):
    def __init__(
        self,
        session: AsyncSession,
        core_cache: CoreMemoryCache,
        redis_cache: RedisClient,
        *args,
        **kwargs,
    ):
        super().__init__(
            session=session,
            core_cache=core_cache,
            redis_cache=redis_cache,
            *args,
            **kwargs,
        )

    def return_value(self, path: AttributePathsModel, values: dict) -> Any:
        """
        From a Python dict, retrieve information using an AttributePathsModel
        object.

        Args:
            path (AttributePathsModel): The path object.
            values (dict): The dict of values.

        Returns:
            Any: The value.
        """
        keys_path = self._get_dict_path(path=path, values=values, keys_path=[])
        ref, key = self._get_nethermost_dict_reference(values, keys_path)
        return ref[key]

    def _get_dict_path(
        self,
        path: AttributePathsModel,
        values: dict,
        keys_path: list = [],
    ) -> list[str | int]:
        """
        Returns a list of elements making up the dictionary "path" to a
        certain element.

        Args:
            path (AttributePathsModel): The original path model.
            values (dict): A dict of values where we want to get the
                value from.
            keys_path (list, optional): Internal use: the keys path.
                Defaults to [].

        Raises:
            HTTPException: If the specified choice index is too high.

        Returns:
            list[str | int]: The list of path elements to be used in a
                Python dict.
        """
        if not path.form:  # root-level attribute update
            keys_path.append(path.attribute)

            return keys_path

        # recurse if path has sub-paths
        if path.sub_path is not None:
            choice_row_index = self._get_choice_index(path=path, values=values)
            keys_path.extend([path.form, choice_row_index])
            self._get_dict_path(
                path=path.sub_path,
                values=values[path.form][choice_row_index],
                keys_path=keys_path,
            )
            # return after deepest path is reached
            return keys_path

        # element of form with choice
        if path.choice.value:
            choice_row_index = self._get_choice_index(path=path, values=values)
            keys_path.extend([path.form, choice_row_index, path.attribute])

            return keys_path

        # element of form with no choice
        elif path.choice.index is not None:
            if values[path.form] is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "restatement": (
                            f"No record for form {values[path.form]!r}"
                        )
                    },
                )
            # check form has the row we're looking for
            if len(values[path.form]) < path.choice.index:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "restatement": (
                            f"Form {path.form!r} does not contain index"
                            f" {path.choice.index!r}"
                        )
                    },
                )
            keys_path.extend([path.form, path.choice.index, path.attribute])

            return keys_path

        return keys_path

    @classmethod
    def _get_choice_index(
        cls,
        path: AttributePathsModel,
        values: dict,
        raise_exception: bool = True,
    ) -> int | None:
        """
        Value is inside an element of a sub-form.

        To get the right element, we check the choice value of a choice
        field in the same element, and in case of multiple elements with
        the same choice value for the same choice field, we filter by
        path.choice.index.

        Args:
            path (AttributePathsModel): The path object.
            values (dict): The values to look into.

        Raises:
            HTTPException: If form does not have enough elements.
            HTTPException: If form does not have enough elements with
                the same choice value for the same choice field.

        Returns:
            int: The choice row index.
        """
        if len(values[path.form]) < path.choice.index:
            if not raise_exception:
                return None

            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "field_path": (
                        f"Form '{path.form}' does not contain index"
                        f" '{path.choice.index}'"
                    )
                },
            )
        choice_rows = [
            row
            for row in values[path.form]
            if row[path.choice.field] == path.choice.value
        ]
        if len(choice_rows) - 1 < path.choice.index:
            if not raise_exception:
                return None

            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "field_path": (
                        f"'{path.form}' only has {len(choice_rows)} rows"
                        f" with value '{path.choice.value}' on field"
                        f" '{path.choice.field}'"
                    )
                },
            )
        choice_row = choice_rows[path.choice.index]

        return values[path.form].index(choice_row)

    @classmethod
    def _get_nethermost_dict_reference(
        cls, ref: dict, keys: list[str | int]
    ) -> tuple[dict, str | int]:
        """
        From a list of elements making up the dictionary path to the
        element of a dictionary, get the reference to the penultimate
        sub-tree and the key to the last leaf.

        Args:
            ref (dict): The dict values.
            keys (list[str  |  int]): The path keys.

        Returns:
            tuple[dict, str | int]: A tuple holding the reference to the
                penultimate sub-tree and the key of the last leaf.
        """
        last_key = ""
        for i, key in enumerate(keys):
            last_key = key
            if i + 1 < len(keys):
                if isinstance(ref, dict):
                    ref = ref.get(key, ref)
                else:
                    ref = ref[key]
        return ref, last_key

    @classmethod
    def _strip_fields(
        cls,
        obj: dict,
        paths: list[AttributePathsModel],
        raise_exception: bool = True,
        export: bool = False,
    ) -> dict:
        converted_obj = convert_keys_to_str(obj)
        stripped: dict[str, list | Any] = orjson.loads(
            orjson.dumps(converted_obj)
        )
        for k, v in obj.items():
            if k in [path.attribute for path in paths]:
                # key is wanted attribute: don't strip
                continue
            if k not in [path.form for path in paths] or v is None:
                del stripped[k]
            else:
                stripped[k] = []
                form_paths = [path for path in paths if path.form == k]
                for this_path in form_paths:
                    if this_path.choice.value:
                        choice_row_index = cls._get_choice_index(
                            path=this_path,
                            values=obj,
                            raise_exception=raise_exception,
                        )
                        if export:
                            if choice_row_index is None:
                                choice_row_index = this_path.choice.index
                    else:
                        choice_row_index = this_path.choice.index
                    values = None
                    if this_path.sub_path and (choice_row_index is not None):
                        # values = {}
                        values = cls._strip_fields(
                            obj=v[choice_row_index],
                            paths=[
                                paths.pop(paths.index(path)).sub_path
                                for path in form_paths
                                if path in paths
                                and path.sub_path
                                and this_path.choice == path.choice
                            ],  # type: ignore
                            export=export,
                        )
                        if values:
                            values[this_path.choice.field] = (
                                this_path.choice.value
                            )
                    elif choice_row_index is not None:
                        values = {}
                        for path in [
                            # remove from paths so we don't come here again
                            paths.pop(paths.index(path))
                            # only consider paths of this "form"
                            for path in form_paths
                            # cover case in which path in form_paths
                            # but not in paths
                            if path in paths
                            # choice is the same
                            and this_path.choice == path.choice
                        ]:
                            values[path.attribute] = v[choice_row_index].get(
                                path.attribute, None
                            )
                            if path.choice.field:
                                values[path.choice.field] = path.choice.value
                    if values:
                        stripped[k].append(values)

                # if no values were appended (there are no requested
                # fields in the sub-forms), remove the key
                if not stripped.get(k, []):
                    del stripped[k]
        return stripped

    async def _get_restatement_row(
        self,
        submission_id: int,
        path: AttributePathsModel,
    ) -> int:
        """
        Returns the exact ID in the DB for the requested row.

        Args:
            submission_id (int): The submission's ID.
            path (AttributePathsModel): The path object.

        Raises:
            HTTPException: If no column definition is found for the attribute.
            HTTPException: If no rows are found.
            HTTPException: If no row with the specified index is found.

        Returns:
            int: The row ID from the database.
        """
        # Recurse if path has sub-paths
        if path.sub_path is not None:
            path.sub_path.row_id = await self._get_restatement_row(
                submission_id=submission_id,
                path=path.sub_path,
            )
        columns = await self.static_cache.column_defs_by_name()
        if path.attribute not in columns:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "restatements": (
                        f"No column def found for attribute '{path.attribute}'"
                    )
                },
            )
        column = columns[path.attribute]
        table_def = column.table_def
        if path.form:
            column = columns[path.form]
            table_defs = await self.static_cache.table_defs()
            table_def = table_defs[column.attribute_type_id]

        # Determine the form name, considering inheritance
        form_name = table_def.name
        if table_def.heritable:
            form_name += "_heritable"

        # Build the SQLAlchemy query
        form_table = await self.static_cache.get_form_table(form_name)

        stmt = select(form_table.c.id).where(
            form_table.c.obj_id == submission_id
        )

        if path.choice.value:  # add choice filter
            stmt = stmt.where(
                form_table.c[path.choice.field] == path.choice.value
            )

        # Execute the query asynchronously
        rows = await self.session.scalars(
            stmt,
            {
                "submission_id": submission_id,
                "choice_value": (
                    path.choice.value if path.choice.value else None
                ),
            },
        )
        rows = rows.all()

        # Consistency checks
        if not rows:
            error_message = (
                "Cannot create revision on an empty submission attribute"
                f" '{path.attribute}'. Use update submission API instead."
            )
            if path.choice.value:
                error_message = (
                    "Cannot create revision on an empty submission attribute"
                    f" '{path.choice.field}' with choice"
                    f" '{path.choice.value}'. Use update submission API"
                    " instead."
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"restatements": error_message},
            )

        if len(rows) < path.choice.index:
            error_message = (
                f"No row with index '{path.choice.index}' for table"
                f" '{form_name}'"
            )
            if path.choice.value:
                error_message += (
                    f" and choice '{path.choice.value}' for attribute"
                    f" '{path.choice.field}'"
                )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"restatements": error_message},
            )

        return rows[path.choice.index]

    async def _unpack_restatement_path(
        self,
        submission_id: int,
        restatement_path: str,
    ) -> AttributePathsModel:
        """
        Extension of `unpack_field_path` for restatements: gets the
        row id from the database for a restatement.

        Args:
            submission_id (int): The submission ID.
            columns (ColumnDefsDataByName): The DB columns.
            restatement_path (str): The restatement path as string.

        Returns:
            AttributePathsModel: The restatement path as an
                AttributePathsModel object.
        """
        path = AttributePathsModel.unpack_field_path(
            field_path=restatement_path
        )
        path.row_id = await self._get_restatement_row(
            submission_id=submission_id,
            path=path,
        )

        return path

    async def unpack_restatement_path_for_restated_col(
        self,
        submission_id: int,
        restatement_path: str,
    ) -> AttributePathsModel:
        """
        Extension of `_unpack_restatement_path` for restatements: gets the
        row id from the database for a restatement, for use of
        export and data source.
        """
        return await self._unpack_restatement_path(
            submission_id=submission_id,
            restatement_path=restatement_path,
        )
