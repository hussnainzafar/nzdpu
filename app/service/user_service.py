import csv
import tempfile

from sqlalchemy import select

from app.db.models import Tracking


class UserService:
    def __init__(self, db_manager):
        self._session = db_manager.get_session()

    async def download_tracking_data_csv(self):
        tracking_data = (
            await self._session.scalars(
                select(Tracking).distinct(Tracking.user_email)
            )
        ).all()
        temp_file = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        with open(temp_file.name, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["user_email"])
            for item in tracking_data:
                writer.writerow([item.user_email])
        return temp_file
