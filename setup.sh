#!/bin/bash

start_api_and_run() {
    uvicorn app.main:app --port 8000 &
    API_PID=$!

    sleep 5

    $1

    kill $API_PID
}

python -m cli.manage_db drop-all -y &&
alembic upgrade head &&
python -m cli.manage_db create-all &&
python -m cli.manage_db create-user testadmin testpass --superuser &&
python -m cli.import_organizations "./tests/data/wis_organization.csv" &&
python -m cli.manage_db create-organizations-aliases &&
python -m cli.manage_forms create tests/data/nzdpu-v40.json &&
python -m cli.create_data_models "NZDPU Core" 1 &&
start_api_and_run "python -m cli.ingest_submissions_via_api ./submissions testadmin testpass"