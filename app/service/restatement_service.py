import re

from sqlalchemy import select

from app.db.database import DBManager
from app.db.models import Restatement


class RestatementService:
    def __init__(self, db_manager: DBManager):
        self._session = db_manager.get_session()

    async def get_restatements_by_submission_ids(
        self, submissions_ids: list[int]
    ):
        stmt = (
            select(Restatement)
            .where(Restatement.obj_id.in_(submissions_ids))
            .order_by(Restatement.obj_id.asc())
        )
        result = await self._session.execute(stmt)
        restatements = result.scalars().all()

        return restatements

    def _get_position_from_attribute_name(
        self, attribute_name: str
    ) -> int | None:
        pattern = r"\{::(\d+)\}"

        match = re.search(pattern, attribute_name)

        if match:
            position = match.group(1)  # Extract the first capturing group
            return int(position)
        else:
            return None

    def get_attribute_name_last_update_mapper_for_tgt(
        self, restatements: list[Restatement], position: int | None = None
    ):
        attribute_name_last_update_dict: dict[str, str] = {}

        for restatement in restatements:
            # restatements are hold with whole path, we need only the last attribute name
            splitted = restatement.attribute_name.split(".")
            if len(splitted) > 0 and restatement.attribute_name.startswith(
                "tgt"
            ):
                key = splitted[-1]
                position_in_atr = self._get_position_from_attribute_name(
                    restatement.attribute_name
                )
                if position == position_in_atr:
                    attribute_name_last_update_dict[key] = (
                        restatement.reporting_datetime
                    )

        return attribute_name_last_update_dict

    def get_attribute_name_last_source_mapper_for_tgt(
        self, restatements: list[Restatement], position: int | None = None
    ):
        attribute_name_last_source_dict: dict[str, str] = {}

        for restatement in restatements:
            # restatements are hold with whole path, we need only the last attribute name
            splitted = restatement.attribute_name.split(".")
            if len(splitted) > 0 and restatement.attribute_name.startswith(
                "tgt"
            ):
                key = splitted[-1]
                position_in_atr = self._get_position_from_attribute_name(
                    restatement.attribute_name
                )
                if position == position_in_atr:
                    attribute_name_last_source_dict[key] = (
                        restatement.data_source
                    )

        return attribute_name_last_source_dict
