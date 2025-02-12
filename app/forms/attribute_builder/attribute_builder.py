"""Attribute builder"""

from abc import ABC, abstractmethod

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AttributePrompt, Choice, ColumnDef, ColumnView
from app.schemas.column_def import AttributeType
from app.schemas.create_form import (
    CreateAttribute,
    CreateAttributeView,
    CreateChoice,
    CreatePrompt,
)


class AttributeBuilder(ABC):
    """
    An abstract attribute builder. Concrete builders inherit from it.
    """

    def __init__(self, language_code: str = "en_US"):
        """
        Initialize this instance
        """

        self.language_code = language_code

    @abstractmethod
    def get_supported_types(self) -> list[str]:
        """
        Return the list of attribute types this forms is responsible for
        :return: list of attribute types
        """

    async def create_attribute(
        self,
        spec: CreateAttribute,
        form_id: int,
        view_id: int,
        user_id: int,
        session: AsyncSession,
        attribute_type_id: int | None = None,
    ) -> int:
        """
        Creates records in the database for a new attribute and related view.

        Parameters
            spec - attribute specification
            form_id - table definition identifier
            view_id - table view identifier
            user_id - owner identifier
            session - database session
            attribute_type_id - the sub-form identifier for attributes of type "form"
        """

        assert (
            spec.type not in [AttributeType.FORM, AttributeType.MULTIPLE]
            or attribute_type_id
        )

        # creates the column
        column_def = ColumnDef(
            table_def_id=form_id,
            name=spec.name,
            user_id=user_id,
            attribute_type=spec.type,
        )
        if attribute_type_id:
            # set reference to the sub-form
            column_def.attribute_type_id = attribute_type_id

        session.add(column_def)
        await session.flush()

        # create column view
        attribute_id: int = column_def.id
        view_spec = spec.view if spec.view else CreateAttributeView()
        constraint_value = (
            [cv.model_dump() for cv in view_spec.constraint_value]
            if view_spec.constraint_value
            else []
        )
        constraint_view = (
            view_spec.constraint_view if view_spec.constraint_view else {}
        )
        column_view = ColumnView(
            column_def_id=attribute_id,
            table_view_id=view_id,
            user_id=user_id,
            constraint_value=constraint_value,
            constraint_view=constraint_view,
        )
        session.add(column_view)
        await session.flush()

        prompts = spec.prompts
        if prompts:
            # create prompts
            await self.create_prompts(attribute_id, prompts, session)

        return column_def.id

    async def create_prompts(
        self,
        attribute_id: int,
        prompts: list[CreatePrompt],
        session: AsyncSession,
    ):
        """
        Creates a new list of prompts for an attribute

        Parameters
            attribute_id - column identifier of the attribute
            prompts - list of prompts we want to attach to the attribute
            session - database session
        """

        prompt_set: list[AttributePrompt] = []
        for prompt in prompts:
            # create prompt
            prompt_set.append(
                AttributePrompt(
                    column_def_id=attribute_id,
                    value=prompt.value,
                    description=prompt.description,
                    language_code=self.language_code,
                )
            )

        # create prompts
        session.add_all(prompt_set)
        # flush transaction
        await session.flush()

    async def create_choices_set(
        self, choices: list[CreateChoice], session: AsyncSession, col_id: int
    ) -> int:
        """
        Creates a new choices set

        Parameters
            choices - list of choices we want to include in the set
            session - database session

        Returns
            identifier of the new choices set, or 0 if no choices set was created
        """

        set_id: int = 0

        if choices:
            # get current max values
            stmt_max_set_id = select(func.max(Choice.set_id))
            result_max_set_id = await session.execute(stmt_max_set_id)
            max_set_id = (
                result_max_set_id.scalars().first() if result_max_set_id else 0
            )
            set_id = max_set_id + 1 if max_set_id else 1
            rank = 1
            # bind column to choices set
            column_rec = await session.get(ColumnDef, col_id)
            assert column_rec
            column_rec.choice_set_id = set_id
            choice_set: list[Choice] = []
            for choice in choices:
                if not choice.choice_id:
                    # undefined choice identifier
                    raise ValueError(
                        f"undefined choice_id on choice: '{choice.value}"
                    )
                # look for duplicate choices in the set (note that the language code is always the same)
                dup_choices = [
                    ch
                    for ch in choice_set
                    if ch.choice_id == choice.choice_id and ch.set_id == set_id
                ]
                if dup_choices:
                    # duplicated choice
                    raise ValueError(
                        f"duplicated choice ({choice.choice_id}, {set_id},"
                        f" '{self.language_code}')"
                    )

                # create choice
                choice_set.append(
                    Choice(
                        choice_id=choice.choice_id,
                        set_id=set_id,
                        set_name=choice.set_name,
                        value=choice.value,
                        order=rank,
                        description=choice.description,
                        language_code=self.language_code,
                    )
                )
                rank = rank + 1

            # create choice set
            session.add_all(choice_set)
            # commit transaction
            await session.commit()

        return set_id

    async def check_duplicates(
        self, spec: CreateAttribute, form_id: int, session: AsyncSession
    ):
        """
        Check that an attribute definition doesn't exist already
        Parameters
        ----------
        spec - specification of the column to check
        form_id - form identifier
        session - database session
        Raises
        ------
        ValueError if the attribute already exists
        """
        stmt = (
            select(ColumnDef)
            .where(ColumnDef.table_def_id == form_id)
            .where(ColumnDef.name == spec.name)
        )
        result = await session.execute(stmt)
        column_rec = result.scalars().first()
        if column_rec:
            # duplicated column
            raise ValueError(
                f"column '{spec.name}' already exists in this table definition"
            )

    async def build(
        self,
        spec: CreateAttribute,
        form_id: int,
        view_id: int,
        user_id: int,
        session: AsyncSession,
    ) -> int:
        """
        Build a new attribute

        Parameters
        spec - specification of the column being built
        form_id - form identifier
        view_id - form view identifier
        user_id - user identifier
        session - database session

        Return
        the new attribute identifier
        """

        # check column type
        attribute_type: str = spec.type
        if attribute_type not in self.get_supported_types():
            raise ValueError(f"unexpected attribute type '{attribute_type}'")

        # check attribute definition doesn't exist already
        await self.check_duplicates(spec, form_id, session)

        # create the column
        return await self.create_attribute(
            spec, form_id, view_id, user_id, session
        )
