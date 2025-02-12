from app.db.models import ColumnDef
from app.dependencies import StaticCache


class ValidatorService:
    def __init__(self, static_cache: StaticCache):
        self.static_cache = static_cache

    def _validated_values_by_column_defs(
        self,
        values: dict,
        column_defs_by_name: dict[str, ColumnDef],
        invalid_attributes: set[str],
    ):
        for key in values:
            if key not in column_defs_by_name:
                invalid_attributes.add(key)
                continue

            if isinstance(values[key], list):
                for item in values[key]:
                    self._validated_values_by_column_defs(
                        item, column_defs_by_name, invalid_attributes
                    )

    async def validate_submission_values(self, values: dict):
        column_defs_by_name = await self.static_cache.column_defs_by_name()
        invalid_attributes: set[str] = set()

        self._validated_values_by_column_defs(
            values, column_defs_by_name, invalid_attributes
        )

        return list(invalid_attributes)
