#!/bin/bash
# BIRD-Interact Environment Reset Script
# This script completely resets the Docker environment and sets up everything from scratch
# Use this when you want to start completely fresh

set -e

echo "🔄 BIRD-Interact Environment Reset"
echo "===================================="
echo "This will:"
echo "  - Stop all containers"
echo "  - Remove all volumes (database data will be lost)"
echo "  - Rebuild containers from scratch"
echo "  - Initialize databases"
echo ""

# Confirm with user
read -p "Are you sure you want to continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Operation cancelled"
    exit 1
fi

echo "🛑 Stopping and removing containers..."
docker compose down -v 2>/dev/null || true

echo "🧹 Cleaning up Docker resources..."
docker system prune -f >/dev/null 2>&1 || true

echo "🏗️  Building and starting containers..."
docker compose up --build -d

echo "⏳ Waiting for services to be ready..."
sleep 10

echo "🔧 Setting up databases..."
./setup-databases.sh

echo ""
echo "✅ Environment reset completed successfully!"
echo ""
echo "🚀 Next steps:"
echo "  1. Set up your API keys in bird_interact_conv/code/config.py"
echo "  2. Run experiments from bird_interact_conv/pipeline/"
echo ""