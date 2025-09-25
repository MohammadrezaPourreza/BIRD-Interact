#!/bin/bash
# BIRD-Interact Database Setup Script
# This script ensures that the PostgreSQL databases are properly initialized
# Run this after starting the Docker containers

set -e

echo "🔧 BIRD-Interact Database Setup"
echo "================================"

# Check if Docker Compose is available
if ! command -v docker compose &> /dev/null; then
    echo "❌ Error: docker compose is not available"
    exit 1
fi

# Check if containers are running
echo "📊 Checking container status..."
if ! docker compose ps postgresql | grep -q "Up"; then
    echo "❌ Error: PostgreSQL container is not running"
    echo "💡 Please start the containers first:"
    echo "   cd evaluation && docker compose up -d"
    exit 1
fi

echo "✅ PostgreSQL container is running"

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL to be ready..."
timeout=60
counter=0
while ! docker compose exec postgresql pg_isready -h localhost -p 5432 -U root >/dev/null 2>&1; do
    sleep 2
    counter=$((counter + 2))
    if [ $counter -ge $timeout ]; then
        echo "❌ Error: PostgreSQL did not become ready within $timeout seconds"
        exit 1
    fi
    echo "   Waiting... ($counter/$timeout seconds)"
done

echo "✅ PostgreSQL is ready"

# Check if template databases exist
echo "🔍 Checking template databases..."
TEMPLATE_DBS=("museum_template" "polar_template" "gaming_template" "crypto_template" "virtual_template")
missing_templates=()

for template_db in "${TEMPLATE_DBS[@]}"; do
    if ! docker compose exec postgresql psql -U root -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$template_db'" | grep -q 1; then
        missing_templates+=("$template_db")
    fi
done

if [ ${#missing_templates[@]} -gt 0 ]; then
    echo "⚠️  Missing template databases: ${missing_templates[*]}"
    echo "🔧 Running database initialization..."
    
    # Run the initialization script
    docker compose exec postgresql /usr/local/bin/check-and-init-db.sh
    
    echo "✅ Database initialization completed"
else
    echo "✅ All template databases are present"
fi

# Verify the fix by testing database reset functionality
echo "🧪 Testing database reset functionality..."
docker compose exec interact_eval_env python -c "
import sys
sys.path.append('/app/evaluation/src')
from postgresql_utils import reset_and_restore_database

try:
    reset_and_restore_database('museum', '123123')
    print('✅ Database reset functionality is working correctly')
except Exception as e:
    print(f'❌ Database reset test failed: {e}')
    sys.exit(1)
" 2>/dev/null || {
    echo "❌ Database reset test failed"
    echo "💡 Make sure the interact_eval_env container is running"
    exit 1
}

echo ""
echo "🎉 Database setup completed successfully!"
echo "📝 Summary:"
echo "   ✅ PostgreSQL container is running"
echo "   ✅ Template databases are initialized"  
echo "   ✅ Database reset functionality is working"
echo ""
echo "🚀 Your BIRD-Interact environment is ready to use!"