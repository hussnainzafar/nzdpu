from typing import Any

from sqlalchemy import Case, or_, select, text

from app.db.database import DBManager
from app.db.models import AuthRole, Organization, User
from app.schemas.organization import (
    OrganizationGet,
    OrganizationGetWithNonLeiIdentifiers,
)


class OrganizationService:
    def __init__(self, db_manager: DBManager):
        self._session = db_manager.get_session()

    @staticmethod
    def get_select_fuzzy_match_stmt(
        search_str: str, select_arguments: list[Any]
    ):
        # fuzzy search for legal name
        fuzzy_search_legal_name_query = (
            "SIMILARITY(METAPHONE(legal_name,10), METAPHONE(:search_str,10))"
        )
        fuzzy_search_legal_name_then_stm = (
            text(f"{fuzzy_search_legal_name_query}")
            .bindparams(search_str=search_str)
            .compile(compile_kwargs={"literal_binds": True})
            .statement
        )
        fuzzy_search_legal_name_where_stm = (
            text(f"{fuzzy_search_legal_name_query} >= 0.3")
            .bindparams(search_str=search_str)
            .compile(compile_kwargs={"literal_binds": True})
            .statement
        )

        # fuzzy search for alias
        fuzzy_search_alias_query = "SIMILARITY(METAPHONE(wis_organization_alias.alias,10), METAPHONE(:search_str,10))"
        fuzzy_search_alias_then_stm = (
            text(f"{fuzzy_search_alias_query}")
            .bindparams(search_str=search_str)
            .compile(compile_kwargs={"literal_binds": True})
            .statement
        )
        fuzzy_search_alias_where_stm = (
            text(f"{fuzzy_search_alias_query} >= 0.3")
            .bindparams(search_str=search_str)
            .compile(compile_kwargs={"literal_binds": True})
            .statement
        )
        fuzzy_search_alias_case_stm = (
            text(
                f"{fuzzy_search_alias_query} >= {fuzzy_search_legal_name_query}"
            )
            .bindparams(search_str=search_str)
            .compile(compile_kwargs={"literal_binds": True})
            .statement
        )

        # exact match for lei
        fuzzy_search_lei_query = "wis_organization.lei = :search_str"
        fuzzy_search_lei_stm = (
            text(f"{fuzzy_search_lei_query}")
            .bindparams(search_str=search_str)
            .compile(compile_kwargs={"literal_binds": True})
            .statement
        )

        # if lei matching exactly then just show the maximum score which is 1,
        # if alias matching has a score higher than legal_name matching score show alias score
        # otherwise show legal_name score
        # this score is then used to order the results by higher matching
        score_case_expression = Case(
            (
                fuzzy_search_lei_stm,
                1,
            ),
            (
                fuzzy_search_alias_case_stm,
                fuzzy_search_alias_then_stm,
            ),
            else_=fuzzy_search_legal_name_then_stm,
        )

        match_by_case_expression = Case(
            (
                fuzzy_search_lei_stm,
                "lei",
            ),
            (
                fuzzy_search_alias_case_stm,
                "alias",
            ),
            else_="legal_name",
        )

        score_label = "score"
        stmt = select(
            score_case_expression.label(score_label),
            match_by_case_expression.label("match_type"),
            *select_arguments,
        )

        stmt = stmt.where(
            or_(
                fuzzy_search_legal_name_where_stm,
                fuzzy_search_alias_where_stm,
                fuzzy_search_lei_stm,
            )
        )

        return (stmt, score_label)

    @staticmethod
    def get_format_sql_func(string: str):
        # replace accent chars with ascii chars, replace -_ with space, remove .,/%+;
        return f"REGEXP_REPLACE(REGEXP_REPLACE(unaccent({string}), '[-_]', ' ', 'g'), '[.,/%+;]', '', 'g')"

    @staticmethod
    def get_select_sub_string_match_stmt(
        search_str: str, select_arguments: list[Any]
    ):
        # sub string search for legal name
        search_legal_name_query = f"{OrganizationService.get_format_sql_func('legal_name')} ilike ('%' || {OrganizationService.get_format_sql_func(':search_str')} || '%')"
        search_legal_name_stm = (
            text(f"{search_legal_name_query}")
            .bindparams(search_str=search_str)
            .compile(compile_kwargs={"literal_binds": True})
            .statement
        )

        # sub string search for alias
        search_alias_query = f"{OrganizationService.get_format_sql_func('wis_organization_alias.alias')} ilike ('%' || {OrganizationService.get_format_sql_func(':search_str')} || '%')"
        search_alias_stm = (
            text(f"{search_alias_query}")
            .bindparams(search_str=search_str)
            .compile(compile_kwargs={"literal_binds": True})
            .statement
        )

        # exact match for lei
        search_lei_query = "wis_organization.lei = :search_str"
        search_lei_stm = (
            text(f"{search_lei_query}")
            .bindparams(search_str=search_str)
            .compile(compile_kwargs={"literal_binds": True})
            .statement
        )

        match_by_case_expression = Case(
            (
                search_lei_stm,
                "lei",
            ),
            (
                search_legal_name_stm,
                "legal_name",
            ),
            else_="alias",
        )

        stmt = select(
            match_by_case_expression.label("match_type"),
            *select_arguments,
        )

        stmt = stmt.where(
            or_(
                search_legal_name_stm,
                search_alias_stm,
                search_lei_stm,
            )
        )

        return stmt

    async def get_organization_by_lei(self, lei: str):
        stmt = select(Organization).where(Organization.lei == lei)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def filter_non_lei_identifiers_based_on_user_role(
        organization: Organization, current_user: User | None
    ):
        organization_dict = organization.__dict__.copy()

        organization_dict.pop("isics")
        organization_dict.pop("duns")
        organization_dict.pop("gleif")
        organization_dict.pop("sing_id")

        if current_user is None:
            return OrganizationGet(**organization_dict)

        groups = [x.name for x in current_user.groups]
        if AuthRole.ADMIN.value in groups:
            return OrganizationGetWithNonLeiIdentifiers(
                **organization.__dict__
            )

        return OrganizationGet(**organization_dict)
