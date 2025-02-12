"""Form builder"""

from typing import Optional

from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    Table,
    select,
    text,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db.database import Base
from app.db.models import (
    ColumnView,
    TableDef,
    TableView,
)
from app.db.types import COMPOSITE_TYPES, NullTypeState
from app.forms.form_meta import FormMeta
from app.loggers import get_nzdpu_logger
from app.schemas.create_form import (
    CreateAttribute,
    CreateForm,
    CreateFormView,
    ViewRevisionCreate,
)

# pylint: disable = too-many-locals, singleton-comparison
logging = get_nzdpu_logger()


class FormBuilder:
    """
    Provides functionalities for building forms
    """

    def __init__(self, language_code: str = "en_US"):
        """
        Initialize this instance
        """

        self.language_code = language_code

    async def create_attribute(
        self,
        spec: CreateAttribute,
        form_id: int,
        view_id: int,
        user_id: int,
        session: AsyncSession,
    ) -> int:
        """
        Creates a new attribute

        Parameters
        ----------
        spec - the attribute specification
        form_id - form identifier
        view_id - view identifier
        user_id - user identifier
        session -database session
        Returns
        -------
        identifier of the new attribute
        """
        from app.forms.attribute_builder.attribute_build_factory import (
            AttributeBuilderFactory,
        )
        from app.forms.attribute_builder.attribute_builder import (
            AttributeBuilder,
        )

        # get attribute builder
        attribute_type: str = spec.type
        builder: Optional[AttributeBuilder] = (
            AttributeBuilderFactory.get_builder(attribute_type)
        )

        if not builder:
            # cannot find attribute builder
            raise ValueError(
                f"could not find a builder for column type: '{attribute_type}"
            )

        # build column
        builder.language_code = self.language_code
        return await builder.build(spec, form_id, view_id, user_id, session)

    @staticmethod
    async def create_table_view(
        spec: CreateFormView,
        form_id: int,
        active: bool,
        user_id: int,
        session: AsyncSession,
    ) -> int:
        """
        Creates a new table view in the schema

        Parameters
        ----------
        spec - the form view specification
        form_id - form identifier
        user_id - user identifier
        session - database session

        Returns
        -------
        identifier of the new view definition
        """

        # check view definition doesn't exist already
        stmt = select(TableView).where(
            TableView.table_def_id == form_id, TableView.name == spec.name
        )
        result = await session.execute(stmt)
        view_rec = result.scalars().first()
        if view_rec:
            # duplicated view
            raise ValueError(
                f"view '{spec.name}' already exists in this table definition"
            )

        # creates the view
        constraint_view = spec.constraint_view if spec.constraint_view else {}
        table_view = TableView(
            table_def_id=form_id,
            name=spec.name,
            description=spec.description,
            revision=1,
            active=active,
            user_id=user_id,
            constraint_view=constraint_view,
        )
        session.add(table_view)
        await session.flush()
        return table_view.id

    @staticmethod
    def init_data_table(name: str, sub_form: bool = False) -> Optional[Table]:
        """
        Initialize a data table for a form
        :param name: name of the form
        :param sub_form: True if this is a sub-form, False if this is a root form
        :return: the new table definition, or None if a table with the same name already exists
        """

        form_data_name: str = name + "_heritable" if sub_form else name
        logging.debug(f"initializing data table: {form_data_name}")

        # maximum length for identifier name (index in our case) is 63 bytes (1 byte = 1 char)
        # this is why we need this slice of the table name
        obj_id_index_name = f"{form_data_name[0: 56] if len(form_data_name) > 56 else form_data_name}_{FormMeta.f_obj_id}"

        # initialize table
        form_data = Table(
            form_data_name,
            Base.metadata,
            Column(FormMeta.f_id, Integer, primary_key=True),
            Column(
                FormMeta.f_obj_id,
                Integer,
                ForeignKey("wis_obj.id", ondelete="CASCADE"),
                nullable=False,
            ),
            Index(obj_id_index_name, FormMeta.f_obj_id),
            keep_existing=True,
        )

        if sub_form:
            # add field referenced from parent data table
            form_data.append_column(
                Column(FormMeta.f_value_id, Integer), replace_existing=True
            )
            # maximum length for identifier name (index in our case) is 63 bytes (1 byte = 1 char)
            # this is why we need this slice of the table name
            value_id_index_name = f"{form_data_name[0: 54] if len(form_data_name) > 54 else form_data_name}_{FormMeta.f_value_id}"
            if not any(
                idx.name
                for idx in form_data.indexes
                if idx.name == value_id_index_name
            ):
                form_data.append_constraint(
                    Index(
                        value_id_index_name,
                        FormMeta.f_value_id,
                    ),
                )

        return form_data

    @staticmethod
    def add_data_columns(form_data: Table, attribute_spec: CreateAttribute):
        """
        Add attribute column(s) to the data table of a form

        Parameters
        ----------
        form_data - the table to add column(s) to
        attribute_spec - specification of the attribute we are creating data column(s) for
        """

        # get column type
        attribute_type: str = attribute_spec.type
        column_type = FormMeta.get_column_type(attribute_type)
        if column_type:
            # add column
            logging.debug(
                f"creating '{attribute_type}' data column for attribute:"
                f" {attribute_spec.name}"
            )
            form_data.append_column(
                Column(attribute_spec.name, column_type), replace_existing=True
            )

    @staticmethod
    async def create_null_attribute_types_in_db(session: AsyncSession):
        # drop types if exists for a clean create
        for type_id in COMPOSITE_TYPES.keys():
            await session.execute(text(f"DROP TYPE IF EXISTS {type_id};"))

        for type_def in COMPOSITE_TYPES.values():
            await session.execute(
                text(
                    f"CREATE TYPE {type_def.kind} AS {type_def.sql_definition};"
                )
            )

    async def add_default_statement_to_null_type_columns(
        self,
        session: AsyncSession,
        attributes: list[CreateAttribute],
        form_data: Table,
    ):
        for attribute in attributes:
            attribute_type = attribute.type
            if attribute_type in COMPOSITE_TYPES.keys():
                alter_column_query = text(
                    f"ALTER TABLE {form_data.name} "
                    f"ALTER COLUMN {attribute.name} "
                    f"SET DEFAULT (null, '{NullTypeState.LONG_DASH.value}');"
                )
                await session.execute(alter_column_query)

    async def go_build(self, spec: CreateForm, session: AsyncSession) -> int:
        """
        Creates a complete form using a schema specification

        Parameters
        ----------
        spec - the schema specification
        session - database session

        Returns
        -------
        form identifier
        """
        # NOTE: this process is located in lifespan handler in main.py now
        # await self.create_null_attribute_types_in_db(session)

        return await self.build(spec, session)

    async def build(
        self, spec: CreateForm, session: AsyncSession, heritable=False
    ) -> int:
        """
        Creates a complete form using a schema specification

        Parameters
        ----------
        spec - the schema specification
        session - database session
        heritable - heritable form flag

        Returns
        -------
        form identifier
        """

        name = spec.name
        logging.debug(f"creating schema: {name}")

        # check table definition doesn't exist already
        stmt = select(TableDef).where(TableDef.name == name)
        result = await session.execute(stmt)
        schema_rec = result.scalars().first()
        if schema_rec:
            # duplicated schema name
            raise ValueError(f"table '{name}' already exists in the schema")

        # create table definition
        table_def = TableDef(
            name=name,
            description=spec.description,
            user_id=spec.user_id,
            heritable=heritable,
        )
        session.add(table_def)
        await session.flush()
        form_id: int = table_def.id

        # create table view
        default_view_name = f"{name.lower()}_view"
        view_spec = (
            spec.view if spec.view else CreateFormView(name=default_view_name)
        )
        if not view_spec.name:
            # set default view name
            view_spec.name = default_view_name
        logging.debug(
            f"creating table view for schema: {name} ({default_view_name})"
        )
        view_id: int = await FormBuilder.create_table_view(
            spec=view_spec,
            form_id=form_id,
            active=True,
            user_id=spec.user_id,
            session=session,
        )

        # create attributes
        attributes: list[CreateAttribute] = spec.attributes
        logging.debug(
            f"creating {len(attributes)} attributes in schema: {name}"
        )
        for attribute in attributes:
            # create attribute record
            await self.create_attribute(
                spec=attribute,
                form_id=form_id,
                view_id=view_id,
                user_id=spec.user_id,
                session=session,
            )

        # initialize data table
        form_data = self.init_data_table(name, sub_form=heritable)
        if form_data is not None:
            for attribute in attributes:
                # add attribute column(s) to data table
                self.add_data_columns(
                    form_data=form_data, attribute_spec=attribute
                )
            # create table
            await session.execute(CreateTable(form_data))

            # add default values for composite type columns
            await self.add_default_statement_to_null_type_columns(
                session, attributes, form_data
            )

            # create indexes
            for index in form_data.indexes:
                try:
                    await session.execute(CreateIndex(index))
                except OperationalError:
                    # if index is already created
                    continue

        # commit the transaction
        await session.commit()

        return form_id

    @staticmethod
    async def copy_table_view(
        view: TableView, table_def_id: int, session: AsyncSession
    ) -> int:
        """
        Creates a copy of a table view, usually for attaching it to a new form revision
        Parameters
        ----------
        view: the table view we want to create a copy of
        table_def_id: identifier of the table def the copy belongs to
        session: database session

        Returns
        -------
        identifier of the table view copy
        """

        name_copy = view.name + "_copy"
        view_copy = TableView(
            table_def_id=table_def_id,
            name=name_copy,
            description=view.description,
            revision=view.revision,
            active=view.active,
            user_id=view.user_id,
            constraint_view=view.constraint_view,
        )
        session.add(view_copy)
        await session.flush()
        return view_copy.id

    async def create_view_revision(
        self, name: str, session: AsyncSession
    ) -> Optional[ViewRevisionCreate]:
        """
        Creates a new revision of an existing form view

        Parameters
        ----------
        name - name of the form view we want to create a new revision of

        Returns
        -------
        information about the new revision, or None if the original form does not exist
        """

        # load current revisions
        result = await session.execute(
            select(TableView)
            .options(selectinload(TableView.column_views))
            .where(TableView.name == name)
            .order_by(TableView.revision.desc())
        )
        view_rev: TableView = result.scalars().first()
        if not view_rev:
            # original form view not found
            return None

        # get next revision number
        revision: int = view_rev.revision + 1

        logging.info(
            f"creating new revision for schema view {name}: {revision}"
        )
        # create new revision of table view
        table_view = TableView(
            table_def_id=view_rev.table_def_id,
            name=name,
            description=view_rev.description,
            revision=revision,
            active=True,
            user_id=view_rev.user_id,
            constraint_view=view_rev.constraint_view,
        )
        session.add(table_view)
        await session.flush()

        table_view_id: int = table_view.id
        logging.debug(
            f"created table view of revision {revision} with ID:"
            f" {table_view_id}"
        )

        for attribute_view in view_rev.column_views:
            # create copy of attribute view
            attribute_view_copy = ColumnView(
                column_def_id=attribute_view.column_def_id,
                user_id=attribute_view.user_id,
                table_view_id=table_view_id,
                constraint_value=attribute_view.constraint_value,
                constraint_view=attribute_view.constraint_view,
                permissions_set_id=attribute_view.permissions_set_id,
                choice_set_id=attribute_view.choice_set_id,
            )
            session.add(attribute_view_copy)

        # commit the transaction
        await session.commit()

        return ViewRevisionCreate(
            id=table_view.id, name=name, revision=revision
        )

    async def set_active_view_revision(
        self, name: str, revision: int, active: bool, session: AsyncSession
    ):
        """
        Enable or disable a revision of a form view

        Parameters
        ----------
        name - name of the form view we want to enable / disable a revision of
        revision - identifier of the revision we want to enable / disable
        active - True to enable the form view, False to disable it
        session - database session
        """

        # load root view
        result = await session.execute(
            select(TableView)
            .where(TableView.name == name)
            .where(TableView.revision == revision)
        )
        table_view: TableView = result.scalars().first()
        assert table_view

        # update view status
        table_view.active = active

        # commit the transaction
        await session.commit()

    async def enable_view_revision(
        self, name: str, revision: int, session: AsyncSession
    ):
        """
        Enable a revision of a form view

        Parameters
        ----------
        name - name of the form view we want to enable a revision of
        revision - identifier of the revision we want to enable
        """

        await self.set_active_view_revision(
            name, revision, active=True, session=session
        )

    async def disable_view_revision(
        self, name: str, revision: int, session: AsyncSession
    ):
        """
        Disable a revision of a form view

        Parameters
        ----------
        name - name of the form view we want to disable a revision of
        revision - identifier of the revision we want to disable
        """

        await self.set_active_view_revision(
            name, revision, active=False, session=session
        )
