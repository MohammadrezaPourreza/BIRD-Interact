# BIRD-Interact Database Setup Guide

This guide explains how to set up the BIRD-Interact evaluation environment from scratch, including proper database initialization.

## Quick Setup (From Scratch)

1. **Start the Docker containers:**
   ```bash
   cd evaluation
   docker compose up --build -d
   ```

2. **Initialize the databases:**
   ```bash
   ./setup-databases.sh
   ```

That's it! The setup script will automatically:
- Check if PostgreSQL is ready
- Verify all template databases exist
- Run initialization if needed
- Test the database reset functionality

## Manual Setup (If needed)

### Step 1: Build and Start Containers
```bash
cd evaluation
docker compose up --build -d
```

### Step 2: Verify Container Status
```bash
docker compose ps
```
You should see both `bird_interact_postgresql` and `interact_eval_env` containers running.

### Step 3: Initialize Databases (if needed)
If the automatic initialization didn't work, you can run it manually:

```bash
# Check if template databases exist
docker compose exec postgresql psql -U root -d postgres -c "SELECT datname FROM pg_database WHERE datname LIKE '%_template' ORDER BY datname;"

# If templates are missing, run initialization
docker compose exec postgresql /usr/local/bin/check-and-init-db.sh
```

### Step 4: Test Database Reset Functionality
```bash
docker compose exec interact_eval_env python -c "
import sys
sys.path.append('/app/evaluation/src')
from postgresql_utils import reset_and_restore_database
reset_and_restore_database('museum', '123123')
print('✅ Database reset is working!')
"
```

## Troubleshooting

### Problem: "psql: command not found" error
**Solution:** The PostgreSQL client tools are not installed in the evaluation container.
- This is now fixed in the `Dockerfile.so_eval`
- If you still see this error, rebuild the containers: `docker compose up --build`

### Problem: "template database does not exist" error  
**Solution:** The template databases weren't created during initialization.
- Run: `./setup-databases.sh` to fix this automatically
- Or manually run: `docker compose exec postgresql /usr/local/bin/check-and-init-db.sh`

### Problem: Containers won't start
**Solution:** Clean up and restart:
```bash
docker compose down -v  # Remove containers and volumes
docker compose up --build -d  # Rebuild and start
./setup-databases.sh  # Initialize databases
```

### Problem: Database initialization is slow
This is normal - the initialization script needs to import large amounts of data for multiple databases. It may take several minutes to complete.

## What the Setup Does

The setup process:

1. **Builds containers** with all necessary tools:
   - PostgreSQL server with PostGIS extensions
   - Python evaluation environment with PostgreSQL client tools

2. **Initializes template databases** from SQL dumps:
   - `museum_template`, `polar_template`, `gaming_template`, etc.
   - These templates are used to quickly reset databases during evaluation

3. **Verifies functionality** by testing:
   - Database connectivity
   - Template database existence
   - Database reset operations

## Files Created/Modified

- `evaluation/env/check-and-init-db.sh` - Database initialization checker
- `evaluation/setup-databases.sh` - User-friendly setup script  
- `evaluation/env/Dockerfile.so_eval` - Fixed PostgreSQL client installation
- `evaluation/env/Dockerfile.postgresql` - Added initialization scripts

## Usage After Setup

Once setup is complete, you can run BIRD-Interact experiments normally:

```bash
cd bird_interact_conv
# Set up your API keys in code/config.py
cd pipeline  
bash run_gpt.sh
```

The database reset functionality will now work correctly during evaluation.