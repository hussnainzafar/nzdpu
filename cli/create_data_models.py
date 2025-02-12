import asyncio

import typer

from app import settings
from app.db.database import DBManager
from app.db.models import DataModel
from app.loggers import get_nzdpu_logger

settings.setup_logging()
logger = get_nzdpu_logger()

app = typer.Typer()


async def create_data_model_in_db(model_name: str, table_view_id: int):
    _session = DBManager()
    try:
        async with _session.get_session() as session:
            data_model = DataModel(
                name=model_name, table_view_id=table_view_id
            )
            session.add(data_model)
            await session.commit()
            logger.info("Data Model created successfully.")
    except Exception as e:
        logger.error(str(e))


@app.command()
def create_model(model_name: str, table_view_id: int):
    asyncio.run(create_data_model_in_db(model_name, table_view_id))


if __name__ == "__main__":
    app()
