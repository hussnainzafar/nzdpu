"""Dump database CLI."""

import asyncio
import os
import subprocess
import traceback

import typer
from sqlalchemy.sql import text

from app.db.database import DBManager
from app.db.models import AuthRole
from cli.manage_db import async_create_all, async_create_user, async_drop_all
from cli.manage_forms import async_create
from tests.constants import SCHEMA_FILE_NAME

# create CLI app
app = typer.Typer()


def run_shell_command(path):
    """
    Execute a shell command using subprocess.

    Parameters:
    path (str): The path to the SQL file to be executed.

    Example usage:
    run_shell_command("/path/to/your/sql/file.sql")

    This function runs a PostgreSQL command using the psql utility to execute an SQL file.
    It uses environment variables (DB_HOST, DB_USER, DB_NAME) to connect to the database.
    """
    command = [
        "psql "
        "-h "
        f"{os.getenv('LEADER_DB_HOST')} "
        "-U "
        f"{os.getenv('LEADER_DB_USER')} "
        "-d "
        f"{os.getenv('LEADER_DB_NAME')} "
        "-f "
        f"{path}"
    ]
    # Run the command and capture its output
    result = subprocess.run(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    # Check if the command was successful
    if result.returncode == 0:
        print("Command output:")
        print(result.stdout)
    else:
        print("Command failed with error:")
        print(result.stderr)


async def database_queries(path):
    """
    Execute a series of SQL statements and run a shell command.

    Parameters:
    path (str): The path to the SQL file to be executed using a shell command.

    Example usage:
    await database_queries("/path/to/your/sql/file.sql")

    This function performs the following tasks:
    1. Updates the 'wis_user' table by setting 'organization_id' to null.
    2. Deletes all records from the 'wis_organization' table.
    3. Inserts two records into the 'wis_file_registry' table.
    4. Commits the changes to the database.
    5. Executes a shell command to run an SQL file specified by 'path'.
    """
    db_manager = DBManager()
    async with db_manager.get_session() as _session:
        stmt_1 = text("update wis_user set organization_id = null;")
        stmt_2 = text("delete from wis_organization;")
        # Execute the filtered SQL statements
        stmt_4 = text(
            "insert into wis_file_registry values(1, 1, 1,"
            " 'nzdpu-2547di-document-storage', 1, 'now()', 72,"
            " 'aev_statement_example01.pdf');"
        )
        stmt_5 = text(
            "insert into wis_file_registry values(2, 1, 1,"
            " 'nzdpu-2547di-document-storage', 1, 'now()', 72,"
            " 'aev_statement_example02.pdf');"
        )
        await _session.execute(stmt_1)
        await _session.execute(stmt_2)
        await _session.execute(stmt_4)
        await _session.execute(stmt_5)
        await _session.commit()
        run_shell_command(path)


async def async_db_dump(path):
    """
    Perform a database dump operation, creating tables, users, and executing SQL queries.

    Parameters:
    path (str): The path to the SQL file to be executed using a shell command.

    Example usage:
    await async_db_dump("/path/to/your/sql/file.sql")

    This function performs the following tasks:
    1. Deletes all existing database tables.
    2. Creates new database tables.
    3. Creates a series of users in the database.
    4. Creates a complete form model from a JSON specification.
    5. Executes SQL queries specified in the 'database_queries' function using the SQL file at the 'path' location.

    Users are created with the following attributes:
    - 'name': The user's name.
    - 'password': The user's password.
    - 'superuser': Indicates if the user is a superuser.
    - 'role': The user's role in the system.

    The 'database_queries' function is called to execute SQL queries specified in the SQL file.

    Note: Make sure to set up the necessary database connection and session before calling this function.
    """
    users = [
        {
            "name": "testadmin",
            "password": "testpass",
            "superuser": True,
            "role": None,
        },
        {
            "name": "nzdpu",
            "password": "nzdpu",
            "superuser": True,
            "role": None,
        },
        {
            "name": "nzdpu_importer",
            "password": "secret_pass",
            "superuser": True,
            "role": None,
        },
        {
            "name": "testexplorer",
            "password": "testpass",
            "superuser": False,
            "role": AuthRole.DATA_EXPLORER,
        },
        {
            "name": "testpublisher",
            "password": "testpass",
            "superuser": False,
            "role": AuthRole.DATA_PUBLISHER,
        },
        {
            "name": "testeditor",
            "password": "testpass",
            "superuser": False,
            "role": AuthRole.SCHEMA_EDITOR,
        },
    ]
    # 1. delete all existing table
    print("droping the tables ... ")
    await async_drop_all()
    # 2. Create database tables
    print("creating new tables ... ")
    await async_create_all()
    # 3. Create a new users
    print("creating users ... ")
    for user in users:
        await async_create_user(
            name=user["name"],
            password=user["password"],
            superuser=user["superuser"],
            role=user["role"],
        )
    # 4. Create a complete form model from a JSON specification
    print("dump forms ... ")
    await async_create(f"tests/data/{SCHEMA_FILE_NAME}")
    # call database qurries
    print("execute databse quries")
    await database_queries(path)


@app.command()
def db_dump(path: str):
    """
    Dump database content and structure using an SQL file.

        Parameters:
        path (str): The path to the SQL file containing database content and structure.

        Example usage:
        To dump a database, run the following command in the terminal:
        ```
        db_dump /path/to/your/sql/file.sql
        ```

        If the operation is successful, it prints "success" to the console. If an exception occurs, it prints the traceback.

        Note: Make sure to set up the necessary database connection and session configuration before running this command.

    """
    try:
        asyncio.run(async_db_dump(path))
        print("success")
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    app()
