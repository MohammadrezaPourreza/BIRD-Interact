#!/bin/bash
set -e

# Database initialization check and setup script
# This script ensures that template databases are created even if the container
# has been restarted and the init scripts didn't run

PGUSER="root"
PGPASSWORD="123123"
PGHOST="localhost"
PGPORT="5432"

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
until pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" 2>/dev/null; do
    echo "PostgreSQL is unavailable - waiting..."
    sleep 2
done
echo "PostgreSQL is ready!"

# Function to check if a database exists
database_exists() {
    local db_name="$1"
    psql -U "$PGUSER" -h "$PGHOST" -p "$PGPORT" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db_name'" | grep -q 1
}

# List of expected template databases
TEMPLATE_DATABASES=(
    "archeology_template"
    "alien_template"
    "cross_db_template"
    "vaccine_template"
    "gaming_template"
    "museum_template"
    "polar_template"
    "solar_template"
    "robot_template"
    "virtual_template"
    "mental_template"
    "news_template"
    "insider_template"
    "crypto_template"
    "fake_template"
    "cybermarket_template"
    "credit_template"
    "disaster_template"
)

# Check if template databases exist
missing_templates=()
for template_db in "${TEMPLATE_DATABASES[@]}"; do
    if ! database_exists "$template_db"; then
        missing_templates+=("$template_db")
    fi
done

# If any template databases are missing, run the initialization script
if [ ${#missing_templates[@]} -gt 0 ]; then
    echo "Missing template databases detected: ${missing_templates[*]}"
    echo "Running database initialization script..."
    
    # Run the initialization script
    if [ -f "/docker-entrypoint-initdb.d/init-databases_postgresql.sh" ]; then
        cd /docker-entrypoint-initdb.d/
        ./init-databases_postgresql.sh
    else
        echo "ERROR: Initialization script not found!"
        exit 1
    fi
else
    echo "All template databases are present."
fi

echo "Database initialization check completed successfully!"