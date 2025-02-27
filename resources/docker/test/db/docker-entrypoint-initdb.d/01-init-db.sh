#!/bin/sh
set -e

psql -v ON_ERROR_STOP=1 --host "$POSTGRES_HOST" --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
      CREATE DATABASE $DB__TEST__POSTGRES__DATABASE;
	    CREATE USER $DB__TEST__POSTGRES__USER WITH ENCRYPTED PASSWORD '$DB__TEST__POSTGRES__PASSWORD';
	    ALTER DATABASE $DB__TEST__POSTGRES__DATABASE OWNER TO $DB__TEST__POSTGRES__USER;
	    GRANT ALL PRIVILEGES ON DATABASE $DB__TEST__POSTGRES__DATABASE TO $DB__TEST__POSTGRES__USER;
	    GRANT ALL ON SCHEMA public TO $DB__TEST__POSTGRES__USER;
EOSQL
