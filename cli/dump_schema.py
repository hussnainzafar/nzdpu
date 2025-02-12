"""Dump Schema"""

from typing import Annotated

import typer

app = typer.Typer()


@app.command()
def dump_openapi_schema_json(
    destination: Annotated[typer.FileTextWrite, typer.Argument()] = "-",
):
    """Dumps the OpenAPI JSON Schema from the NZDPU-wis application into the destination
    path provided, or stdout by default
    """
    import json
    import os

    # Currently we have to fake some env vars to import the application
    os.environ.update(
        {
            "FB_api_key": "",
            "FB_authDomain": "",
            "FB_database_url": "",
            "FB_storage_bucket": "",
            "REDIS_TTL": "-0",
        }
    )
    from app.main import app

    json.dump(app.openapi(), destination, indent=2)

    print("\n")


if __name__ == "__main__":
    # start CLI App
    app()
