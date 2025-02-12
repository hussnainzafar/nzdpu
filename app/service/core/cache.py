import asyncio
import warnings
from dataclasses import dataclass, field
from typing import Sequence

from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.db.models import (
    AttributePrompt,
    Base,
    Choice,
    ColumnDef,
    ColumnView,
    Organization,
    TableDef,
    TableView,
)


@dataclass
class CacheData:
    organizations: dict[int, Organization] = field(default_factory=dict)
    form_data_tables: dict[str, Table] = field(default_factory=dict)
    table_views: dict[int, TableView] = field(default_factory=dict)
    table_defs: dict[int, TableDef] = field(default_factory=dict)
    table_defs_by_name: dict[str, TableDef] = field(default_factory=dict)
    column_defs_by_name: dict[str, ColumnDef] = field(default_factory=dict)
    column_defs_by_id: dict[int, ColumnDef] = field(default_factory=dict)
    choices: dict[int, Choice] = field(default_factory=dict)
    prompts: dict[int, AttributePrompt] = field(default_factory=dict)


class CoreMemoryCache:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.lock = asyncio.Lock()
        self.cache_data = CacheData()

    def set_organizations(self, orgs: Sequence[Organization]):
        self.cache_data.organizations = {org.nz_id: org for org in orgs}

    def set_table_views(self, views: Sequence[TableView]):
        self.cache_data.table_views = {view.id: view for view in views}

    def set_table_defs(self, table_defs: Sequence[TableDef]):
        self.cache_data.table_defs = {td.id: td for td in table_defs}
        self.cache_data.table_defs_by_name = {td.name: td for td in table_defs}

    def set_column_defs(self, column_defs: Sequence[ColumnDef]):
        self.cache_data.column_defs_by_name = {
            cd.name: cd for cd in column_defs
        }
        self.cache_data.column_defs_by_id = {cd.id: cd for cd in column_defs}

    def set_choices(self, choices: Sequence[Choice]):
        self.cache_data.choices = {
            choice.choice_id: choice for choice in choices
        }

    def set_prompts(self, prompts: Sequence[AttributePrompt]):
        self.cache_data.prompts = {prompt.id: prompt for prompt in prompts}

    async def get_form_data_tables(self):
        async with self.session.bind.begin() as conn:
            with warnings.catch_warnings(action="ignore"):
                await conn.run_sync(Base.metadata.reflect)

            return {
                table_name: obj
                for table_name, obj in Base.metadata.tables.items()
                if not table_name.startswith("wis")
                or table_name in ("wis_aggregated_obj_view", "wis_obj")
            }

    async def load_data(self):
        await self.lock.acquire()
        try:
            table_views_results = (
                (
                    await self.session.scalars(
                        select(TableView)
                        .options(
                            joinedload(TableView.table_def).options(
                                selectinload(
                                    TableDef.columns
                                ).options(  # Use selectinload for better handling of larger sets
                                    selectinload(
                                        ColumnDef.prompts
                                    ),  # Switch to selectinload where possible
                                    selectinload(ColumnDef.choices),
                                    joinedload(
                                        ColumnDef.table_def
                                    ),  # Use joinedload for single relationships
                                    selectinload(ColumnDef.views).options(
                                        joinedload(ColumnView.column_def)
                                    ),
                                )
                            )
                        )
                        .where(TableView.active == True)
                    )
                )
                .unique()
                .all()
            )
            organizations_results = (
                await self.session.scalars(select(Organization))
            ).all()

            form_data_tables = await self.get_form_data_tables()
            self.cache_data.form_data_tables = form_data_tables

            self.set_table_views(table_views_results)
            self.set_organizations(organizations_results)
            self.set_table_defs(
                [view.table_def for view in table_views_results]
            )
            columns = [
                col
                for view in table_views_results
                for col in view.table_def.columns
            ]
            choices = [
                choice
                for col in columns
                for choice in col.choices
                if col.choices
            ]
            prompts = [
                prompt
                for col in columns
                for prompt in col.prompts
                if col.prompts
            ]

            self.set_column_defs(columns)
            self.set_choices(choices)
            self.set_prompts(prompts)

        finally:
            self.lock.release()

    async def form_data_tables(self) -> dict[str, Table]:
        async with self.lock:
            return self.cache_data.form_data_tables

    async def get_form_table(self, name="nzdpu_form"):
        form_tables = await self.form_data_tables()
        return form_tables.get(name)

    async def table_views(self) -> dict[int, TableView]:
        async with self.lock:
            return self.cache_data.table_views

    async def organizations(self) -> dict[int, Organization]:
        async with self.lock:
            return self.cache_data.organizations

    async def table_defs(self) -> dict[int, TableDef]:
        async with self.lock:
            return self.cache_data.table_defs

    async def table_defs_by_name(self) -> dict[str, TableDef]:
        async with self.lock:
            return self.cache_data.table_defs_by_name

    async def column_defs_by_name(self) -> dict[str, ColumnDef]:
        async with self.lock:
            return self.cache_data.column_defs_by_name

    async def column_defs_by_id(self) -> dict[int, ColumnDef]:
        async with self.lock:
            return self.cache_data.column_defs_by_id

    async def choices(self) -> dict[int, Choice]:
        async with self.lock:
            return self.cache_data.choices

    async def prompts(self) -> dict[int, AttributePrompt]:
        async with self.lock:
            return self.cache_data.prompts

    async def refresh_values(self):
        await self.load_data()
