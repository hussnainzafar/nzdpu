from sqlalchemy import func, select

from app.db.database import DBManager
from app.db.models import Organization, SubmissionObj
from app.dependencies import StaticCache


class SearchService:
    def __init__(self, db_manager: DBManager, static_cache: StaticCache):
        self._session = db_manager.get_session()
        self.static_cache = static_cache

    async def count_all_submissions(self) -> int:
        form_table = await self.static_cache.get_form_table()
        search_query = (
            select(func.count())
            .select_from(form_table)
            .join(SubmissionObj, SubmissionObj.id == form_table.c.obj_id)
            .join(Organization, SubmissionObj.nz_id == Organization.nz_id)
        )
        result_query = await self._session.execute(search_query)
        result = result_query.scalar_one_or_none()

        if result is None:
            return 0

        return result
