#!/bin/bash
set -e

# Custom PostgreSQL entrypoint that ensures database initialization
echo "Starting PostgreSQL with database initialization checks..."

# Start PostgreSQL in the background using the official entrypoint
echo "Starting PostgreSQL server..."
docker-entrypoint.sh postgres &
POSTGRES_PID=$!

# Wait for PostgreSQL to be fully ready
echo "Waiting for PostgreSQL to be ready for connections..."
until pg_isready -h localhost -p 5432 -U root 2>/dev/null; do
    echo "PostgreSQL is starting up - waiting..."
    sleep 2
done

# Give PostgreSQL a moment to fully initialize
sleep 5

# Run the database initialization check
echo "Running database initialization check..."
/usr/local/bin/check-and-init-db.sh

echo "PostgreSQL is ready with all databases initialized!"

# Keep the PostgreSQL process running in the foreground
wait $POSTGRES_PID