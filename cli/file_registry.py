"""CLI commands for file management"""

import asyncio

import typer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from app.db.database import DBManager
from app.db.models import Vault

# create CLI app
app = typer.Typer()


# ASYNC FUNCTIONS


async def async_create_vault(
    name: str, storage_type: int, access_type: str, access_data: str
) -> None:
    """
    Asynchronous create_vault.
    """
    session: AsyncSession
    db_manager = DBManager()
    async with db_manager.get_session() as session:
        # check if a vault with the same name already exists
        vault = await session.scalar(select(Vault).filter_by(name=name))
        if vault is not None:
            # if vault already exists
            print("A vault with the name '" + name + "' already exists!")
        else:
            # create new vault
            vault = Vault(
                name=name,
                storage_type=storage_type,
                access_data=access_data,
                access_type=access_type,
            )
            session.add(vault)
            await session.commit()


async def async_update_vault(
    vault_id: int,
    name: str,
    storage_type: int,
    access_type: str,
    access_data: str,
) -> None:
    """
    Asynchronous update_vault.
    """

    db_manager = DBManager()
    async with db_manager.get_session() as session:
        # check if the vault exists
        vault = await session.scalar(select(Vault).filter_by(id=vault_id))
        if vault is not None:
            # if vault exists
            if name not in ("", vault.name):
                vault.name = name
            if storage_type not in (0, vault.storage_type):
                vault.storage_type = storage_type
            if access_type not in ("google_adc", vault.access_type, ""):
                vault.access_type = access_type
            if access_data not in ("", vault.access_data):
                vault.access_data = access_data
            session.add(vault)
            await session.commit()
        else:
            print("Vault ", id, " was not found.")
            # if vault does not exist
            print("Vault ", vault_id, " was not found.")


# SYNC COMMANDS


@app.command()
def create_vault(
    name: str,
    storage_type: Annotated[int, typer.Argument()] = 0,
    access_type: Annotated[str, typer.Argument()] = "google_adc",
    access_data: Annotated[str, typer.Argument()] = "",
) -> None:
    """
    Create Vault.

    Parameters:
        name - (str)(required)
        storage_type - (int)
        access_type - (str)
        access_data - (str)
    """

    asyncio.run(
        async_create_vault(
            name=name,
            storage_type=storage_type,
            access_type=access_type,
            access_data=access_data,
        )
    )


@app.command()
def update_vault(
    vault_id: int,
    name: Annotated[str, typer.Argument()] = "",
    storage_type: Annotated[int, typer.Argument()] = 0,
    access_type: Annotated[str, typer.Argument()] = "google_adc",
    access_data: Annotated[str, typer.Argument()] = "",
) -> None:
    """
    Update Vault.

    Parameters:
        id - (int)(required)
        name - (str)
        storage_type - (int)
        access_type - (str)
        access_data - (str)
    """

    asyncio.run(
        async_update_vault(
            vault_id=vault_id,
            name=name,
            storage_type=storage_type,
            access_type=access_type,
            access_data=access_data,
        )
    )


if __name__ == "__main__":
    # start CLI App
    app()
