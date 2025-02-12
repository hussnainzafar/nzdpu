from dictdiffer import diff
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SubmissionObj
from app.db.redis import RedisClient
from app.loggers import get_nzdpu_logger
from app.service.core.cache import CoreMemoryCache
from app.service.core.loaders import SubmissionLoader


class AggregatedObjectViewValidator:
    def __init__(
        self,
        session: AsyncSession,
        static_cache: CoreMemoryCache,
        redis_cache: RedisClient,
    ) -> None:
        self.logger = get_nzdpu_logger()
        self.session = session
        self.static_cache = static_cache
        self.redis_cache = redis_cache

    async def validate(self, submission_id: int) -> bool:
        loader = SubmissionLoader(
            self.session, self.static_cache, self.redis_cache
        )
        submission_db = await loader.load(submission_id, db_only=True)
        submission_aggregated = await loader.load(
            submission_id, use_aggregate=True
        )

        differences = list(
            diff(
                submission_db.model_dump(), submission_aggregated.model_dump()
            )
        )

        if differences:
            self.logger.error(
                "AggregatedObjectViewValidator: Submission is invalid",
                submission_id=submission_id,
                differences=differences,
            )
            return {"differences": differences, "submission_id": submission_id}
        return True

    async def validate_all(self, offset: int, limit: int) -> dict:
        total = (
            await self.session.execute(func.count(SubmissionObj.id))
        ).scalar()

        submissions = (
            (
                await self.session.execute(
                    select(SubmissionObj.id)
                    .order_by(SubmissionObj.id)
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        invalid_submissions = []
        for submission_id in submissions:
            result = await self.validate(submission_id)
            if result is not True:
                invalid_submissions.append(result)

        return {
            "offset": offset,
            "limit": limit,
            "total": total,
            "invalid_submissions": invalid_submissions,
        }
