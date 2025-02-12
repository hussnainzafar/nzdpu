#!/bin/bash

wis_user="wis_user wis_user_group wis_group wis_permission wis_password_history wis_user_request wis_tracking"

get_password() {
    if [ -z "$PGPASSWORD" ]; then
        read -s -p "Enter PostgreSQL password: " PGPASSWORD
        echo
        export PGPASSWORD
    fi
}

# Prompt for password
get_password

get_form_tables() {
    PGPASSWORD=$PGPASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "\dt" | awk '$3 !~ /^wis/ {print $3}' | tr '\n' ' '
}

get_submission_tables() {
    local non_wis=$(get_form_tables)
    echo "wis_obj wis_aggregated_obj_view wis_restatement $non_wis"
}

print_usage() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo " --clean               Clean (drop) database objects before recreating"
    echo " -r, --remove TABLES   Tables to exclude from the dump"
    echo " -o, --only TABLES     Tables to include in the dump (cannot be used with -r)"
    echo " --no-data TABLES      Tables to include in the dump without data"
    echo " -h, --host HOST       Database host"
    echo " -p, --port PORT       Database port"
    echo " -d, --dbname DBNAME   Database name"
    echo " -U, --username USER   Database user"
    echo " -f, --file FILENAME   Output file name"
    echo " -pre, --prefix PREFIX Prefix for the output file name (default: nzdpu)"
    echo " --help                Show this help message"
    echo "Note: TABLES can be space-separated, comma-separated, or predefined sets (wrap in single quotes ''):"
    echo " '\$wis_user': $wis_user"
    echo " '\$wis_submission': (dynamically generated, includes wis_submission, wis_aggregated_obj_view, and all non-wis tables)"
}

parse_tables() {
    local arg="$1"
    case "$arg" in
        '$wis_user')
            echo "$wis_user"
            ;;
        '$wis_submission')
            get_submission_tables
            ;;
        *)
            echo "$arg" | tr ',' ' '
            ;;
    esac
}

REMOVE_TABLES=()
ONLY_TABLES=()
NO_DATA_TABLES=()
DB_HOST="localhost"
DB_PORT="5432"
DB_NAME=""
DB_USER=""
PREFIX="nzdpu"
OUTPUT_FILE=""
CLEAN_OPTION=""

while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --clean)
            CLEAN_OPTION="--clean"
            shift
            ;;
        -r|--remove)
            shift
            while [[ $# -gt 0 && ! "$1" =~ ^- ]]; do
                REMOVE_TABLES+=($(parse_tables "$1"))
                shift
            done
            ;;
        -o|--only)
            shift
            while [[ $# -gt 0 && ! "$1" =~ ^- ]]; do
                ONLY_TABLES+=($(parse_tables "$1"))
                shift
            done
            ;;
        --no-data)
            shift
            while [[ $# -gt 0 && ! "$1" =~ ^- ]]; do
                NO_DATA_TABLES+=($(parse_tables "$1"))
                shift
            done
            ;;
        -h|--host)
            DB_HOST="$2"
            shift 2
            ;;
        -p|--port)
            DB_PORT="$2"
            shift 2
            ;;
        -d|--dbname)
            DB_NAME="$2"
            shift 2
            ;;
        -U|--username)
            DB_USER="$2"
            shift 2
            ;;
        -f|--file)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        -pre|--prefix)
            PREFIX="$2"
            shift 2
            ;;
        --help)
            print_usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            print_usage
            exit 1
            ;;
    esac
done

if [ -z "$OUTPUT_FILE" ]; then
    OUTPUT_FILE="${PREFIX}_dump_$(date +%Y%m%d_%H%M%S).sql"
fi

if [ ${#REMOVE_TABLES[@]} -gt 0 ] && [ ${#ONLY_TABLES[@]} -gt 0 ]; then
    echo "Error: Cannot use both --remove and --only options."
    exit 1
fi

create_pg_dump_cmd() {
    local cmd="PGPASSWORD=$PGPASSWORD pg_dump -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME $CLEAN_OPTION"

    if [ ${#ONLY_TABLES[@]} -gt 0 ]; then
        for table in "${ONLY_TABLES[@]}"; do
            cmd+=" -t $table"
        done
    elif [ ${#REMOVE_TABLES[@]} -gt 0 ]; then
        for table in "${REMOVE_TABLES[@]}"; do
            cmd+=" -T $table"
        done
    fi

    for table in "${NO_DATA_TABLES[@]}"; do
        cmd+=" --exclude-table-data=$table"
    done

    echo "$cmd"
}

PG_DUMP_CMD=$(create_pg_dump_cmd)

echo "Dumping database..."
eval "$PG_DUMP_CMD -f \"$OUTPUT_FILE\""

# Clear the password from the environment
unset PGPASSWORD

echo "Database dump completed successfully. Output file: $OUTPUT_FILE"