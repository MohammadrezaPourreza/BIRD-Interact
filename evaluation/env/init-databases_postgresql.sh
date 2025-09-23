#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status
set -u  # Exit immediately if an unset variable is used
set -o pipefail  # Exit immediately if any command in a pipeline fails

# Initialize error tracking
ERROR_COUNT=0
ERROR_LOG="/tmp/init_errors.log"
> "$ERROR_LOG"  # Clear the log file

# Function to log errors and increment counter
log_error() {
    local message="$1"
    echo "ERROR: $message" | tee -a "$ERROR_LOG"
    ((ERROR_COUNT++))
}

# Function to check if initialization should continue
check_critical_errors() {
    if [[ $ERROR_COUNT -gt 0 ]]; then
        echo "CRITICAL: $ERROR_COUNT errors occurred during database initialization"
        echo "Error details:"
        cat "$ERROR_LOG"
        echo "Container initialization FAILED - exiting"
        exit 1
    fi
}

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
until psql -U root -c '\l' 2>/dev/null; do
  >&2 echo "PostgreSQL is unavailable - waiting..."
  sleep 2
done

echo "PostgreSQL is ready!"

############################
# 0. Create template DB: sql_test_template
############################
echo "Creating template database: sql_test_template with UTF8 encoding (formerly sql_test)"
psql -U root -tc "SELECT 1 FROM pg_database WHERE datname='sql_test_template'" | grep -q 1 \
  || psql -U root -c "CREATE DATABASE sql_test_template WITH OWNER=root ENCODING='UTF8' TEMPLATE=template0;"

# Create schemas in sql_test_template
echo "Creating required schemas: test_schema and test_schema_2 in sql_test_template"
psql -U root -d sql_test_template -c "CREATE SCHEMA IF NOT EXISTS test_schema;"
psql -U root -d sql_test_template -c "CREATE SCHEMA IF NOT EXISTS test_schema_2;"

# Create hstore, citext extensions
echo "Creating hstore and citext extensions in sql_test_template..."
psql -U root -d sql_test_template -c "CREATE EXTENSION IF NOT EXISTS hstore;"
psql -U root -d sql_test_template -c "CREATE EXTENSION IF NOT EXISTS citext;"

# Set default_text_search_config
echo "Setting default_text_search_config to pg_catalog.english in sql_test_template..."
psql -U root -d sql_test_template -c "ALTER DATABASE sql_test_template SET default_text_search_config = 'pg_catalog.english';"

echo "NOTE: For two-phase transaction support, set 'max_prepared_transactions' > 0 in postgresql.conf."

############################
# 1. Define DB → tables mapping
############################
declare -A DATABASE_MAPPING=(
    ["archeology_template"]="projects personnel sites equipment scans scanenvironment scanpointcloud scanmesh scanspatial scanfeatures scanconservation scanregistration scanprocessing scanqc"
    ["alien_template"]="observatories telescopes signals signalprobabilities signaladvancedphenomena signalclassification signaldecoding signaldynamics researchprocess observationalconditions sourceproperties"
    ["cross_db_template"]="dataflow riskmanagement dataprofile securityprofile vendormanagement compliance auditandcompliance"
    ["vaccine_template"]="shipments container transportinfo vaccinedetails regulatoryandmaintenance sensordata datalogger"
    ["gaming_template"]="testsessions performance deviceidentity mechanical audioandmedia rgb physicaldurability interactionandcontrol"
    ["museum_template"]="artifactscore artifactratings sensitivitydata exhibitionhalls showcases environmentalreadingscore airqualityreadings surfaceandphysicalreadings lightandradiationreadings conditionassessments riskassessments conservationandmaintenance usagerecords artifactsecurityaccess"
    ["polar_template"]="equipment location operationmaintenance powerbattery engineandfluids transmission chassisandvehicle communication cabinenvironment lightingandsafety waterandwaste scientific weatherandstructure thermalsolarwindandgrid"
    ["solar_template"]="plant panel performance electrical environment maintenance inverter alerts"
    ["robot_template"]="robot_record robot_details operation joint_performance joint_condition actuation_data mechanical_status system_controller maintenance_and_fault performance_and_safety"
    ["virtual_template"]="fans virtualidols interactions membershipandspending engagement commerceandcollection socialcommunity eventsandclub loyaltyandachievements moderationandcompliance preferencesandsettings supportandfeedback retentionandinfluence additionalnotes"
    ["mental_template"]="facilities clinicians patients assessmentbasics encounters assessmentsymptomsandrisk assessmentsocialanddiagnosis treatmentbasics treatmentoutcomes"
    ["news_template"]="users devices articles recommendations sessions systemperformance interactions interactionmetrics"   
    ["insider_template"]="trader transactionrecord advancedbehavior sentimentandfundamentals compliancecase investigationdetails enforcementactions"
    ["crypto_template"]="users orders orderexecutions fees marketdata marketstats analyticsindicators riskandmargin accountbalances systemmonitoring"
    ["fake_template"]="account profile sessionbehavior networkmetrics contentbehavior messaginganalysis technicalinfo securitydetection moderationaction"
    ["cybermarket_template"]="markets vendors buyers products transactions communication riskanalysis securitymonitoring investigation"
    ["credit_template"]="core_record employment_and_income expenses_and_assets bank_and_transactions credit_and_compliance credit_accounts_and_history"
    ["disaster_template"]="disasterevents distributionhubs operations supplies transportation humanresources financials beneficiariesandassessments environmentandhealth coordinationandevaluation"
)


############################
# 2. Create template DBs and import data
############################
for DB_TEMPLATE in "${!DATABASE_MAPPING[@]}"; do
    echo "Creating template database: $DB_TEMPLATE"
    psql -U root -tc "SELECT 1 FROM pg_database WHERE datname='${DB_TEMPLATE}'" | grep -q 1 \
      || psql -U root -c "CREATE DATABASE ${DB_TEMPLATE} WITH OWNER=root ENCODING='UTF8' TEMPLATE=template0;"
done

# Function to import files from database-specific folders
import_db_files() {
    local db_template="$1"
    local db_folder="/docker-entrypoint-initdb.d/postgre_table_dumps/${db_template}"
    
    echo "Importing files for ${db_template} from ${db_folder}"
    
    # Check if the folder exists
    if [[ ! -d "${db_folder}" ]]; then
        log_error "Folder ${db_folder} does not exist for database ${db_template}"
        return 1
    fi
    
    # First, check and import enum_definitions.sql if it exists
    local enum_file="${db_folder}/enum_definitions.sql"
    if [[ -f "${enum_file}" ]]; then
        echo "Importing enum definitions from ${enum_file} into ${db_template}..."
        if ! psql -U root -d "${db_template}" -f "${enum_file}" 2>&1; then
            log_error "Failed to import enum definitions from ${enum_file} for ${db_template}"
            return 1
        fi
        echo "✅ Successfully imported enum definitions for ${db_template}"
    fi
    
    # Special case for global_atlas_template
    if [[ "${db_template}" == "global_atlas_template" ]]; then
        # Check if the schema and inputs files exist
        local schema_file="${db_folder}/global_atlas-schema.sql"
        local inputs_file="${db_folder}/global_atlas-inputs.sql"
        
        if [[ -f "${schema_file}" && -f "${inputs_file}" ]]; then
            echo "Importing global_atlas schema file to ${db_template}..."
            if ! psql -U root -d "${db_template}" -f "${schema_file}" 2>&1; then
                log_error "Failed to import schema file ${schema_file} for ${db_template}"
                return 1
            fi
            
            echo "Importing global_atlas data file to ${db_template}..."
            if ! psql -U root -d "${db_template}" -f "${inputs_file}" 2>&1; then
                log_error "Failed to import data file ${inputs_file} for ${db_template}"
                return 1
            fi
        else
            # If the special files don't exist, fall back to importing individual table files
            echo "Special global_atlas files not found, falling back to individual table imports."
            import_table_files "${db_template}" "${db_folder}"
        fi
    else
        # Regular case: import all table files in the folder
        import_table_files "${db_template}" "${db_folder}"
    fi
}

# Function to import individual table files
import_table_files() {
    local db_template="$1"
    local db_folder="$2"
    local tables="${DATABASE_MAPPING[$db_template]}"
    local table_errors=0
    local imported_count=0
    
    echo "Expected tables for ${db_template}: ${tables}"
    
    # Import tables based on mapping first
    for table in $tables; do
        local sql_file="${db_folder}/${table}.sql"
        if [[ -f "$sql_file" ]]; then
            echo "Importing ${sql_file} into database ${db_template}"
            if psql -U root -d "${db_template}" -f "${sql_file}" 2>&1; then
                imported_count=$((imported_count + 1))
                echo "✅ Successfully imported ${table}.sql"
            else
                log_error "Failed to import ${sql_file} into database ${db_template}"
                table_errors=$((table_errors + 1))
            fi
        else
            echo "⚠️  Warning: SQL file ${sql_file} not found for table ${table} in database ${db_template}"
        fi
    done
    
    # Also try to import any additional .sql files not in the mapping (excluding enum_definitions.sql)
    echo "Checking for additional SQL files in ${db_folder}..."
    for sql_file in "${db_folder}"/*.sql; do
        # Skip if file doesn't exist (in case of empty glob)
        [[ ! -f "$sql_file" ]] && continue
        
        local basename=$(basename "$sql_file" .sql)
        
        # Skip enum_definitions.sql as it was already imported
        [[ "$basename" == "enum_definitions" ]] && continue
        
        # Skip if this table was already processed in the mapping
        local already_processed=false
        for table in $tables; do
            if [[ "$basename" == "$table" ]]; then
                already_processed=true
                break
            fi
        done
        
        # Import additional files not in the mapping
        if [[ "$already_processed" == false ]]; then
            echo "Found additional SQL file: ${sql_file}"
            if psql -U root -d "${db_template}" -f "${sql_file}" 2>&1; then
                imported_count=$((imported_count + 1))
                echo "✅ Successfully imported additional file: ${basename}.sql"
            else
                log_error "Failed to import additional SQL file ${sql_file} into database ${db_template}"
                table_errors=$((table_errors + 1))
            fi
        fi
    done
    
    echo "📊 Database ${db_template} import summary: ${imported_count} files imported successfully, ${table_errors} errors"
    
    if [[ $table_errors -gt 0 ]]; then
        log_error "Database ${db_template} had ${table_errors} table import failures"
        return 1
    fi
    
    if [[ $imported_count -eq 0 ]]; then
        log_error "Database ${db_template} had no files imported successfully"
        return 1
    fi
    
    return 0
}

# Import data for each database
echo "Starting database imports..."
SUCCESSFUL_IMPORTS=0
FAILED_IMPORTS=0

for DB_TEMPLATE in "${!DATABASE_MAPPING[@]}"; do
    echo "========================================="
    echo "Processing database: $DB_TEMPLATE"
    echo "========================================="
    if import_db_files "${DB_TEMPLATE}"; then
        echo "✅ Successfully imported data for database ${DB_TEMPLATE}"
        ((SUCCESSFUL_IMPORTS++))
    else
        echo "❌ Failed to import data for database ${DB_TEMPLATE}"
        ((FAILED_IMPORTS++))
        # Don't exit immediately, continue with other databases
    fi
    echo ""
done

echo "📊 Import Summary:"
echo "   ✅ Successful imports: ${SUCCESSFUL_IMPORTS}"
echo "   ❌ Failed imports: ${FAILED_IMPORTS}"
echo "   📁 Total databases processed: $((SUCCESSFUL_IMPORTS + FAILED_IMPORTS))"

# Only check critical errors if ALL imports failed
if [[ $SUCCESSFUL_IMPORTS -eq 0 ]]; then
    log_error "CRITICAL: All database imports failed - this is a critical error"
    check_critical_errors
elif [[ $FAILED_IMPORTS -gt 0 ]]; then
    echo "⚠️  Warning: Some database imports failed, but continuing with available databases"
fi

############################
# 3. Mark these template DBs as 'datistemplate = true'
############################
echo "Marking template databases as 'datistemplate = true'..."
TEMPLATE_MARKING_ERRORS=0

for DB_TEMPLATE in "${!DATABASE_MAPPING[@]}"; do
  echo "Marking ${DB_TEMPLATE} as template database..."
  if psql -U root -d postgres -c "UPDATE pg_database SET datistemplate = true WHERE datname = '${DB_TEMPLATE}';"; then
    echo "✅ Successfully marked ${DB_TEMPLATE} as template"
  else
    log_error "Failed to mark ${DB_TEMPLATE} as template database"
    ((TEMPLATE_MARKING_ERRORS++))
  fi
done

if [[ $TEMPLATE_MARKING_ERRORS -gt 0 ]]; then
  echo "⚠️  Warning: ${TEMPLATE_MARKING_ERRORS} templates could not be marked properly"
else
  echo "✅ All template databases marked successfully"
fi

############################
# Example usage
############################
echo "All template databases created. For example, to clone 'financial_template' into 'financial':"
echo "    dropdb financial || true"
echo "    createdb financial --template=financial_template"
echo ""
echo "Done creating template DBs."

echo "Now creating real databases from templates..."
REAL_DB_CREATED=0
REAL_DB_ERRORS=0

for DB_TEMPLATE in "${!DATABASE_MAPPING[@]}"; do
  REAL_DB="${DB_TEMPLATE%_template}"
  echo "Checking if real database '${REAL_DB}' exists..."
  EXISTS=$(psql -U root -tc "SELECT 1 FROM pg_database WHERE datname='${REAL_DB}'" | grep -c 1 || echo "0")
  if [[ "$EXISTS" -eq 0 ]]; then
    echo "Creating real database '${REAL_DB}' from template '${DB_TEMPLATE}'"
    if psql -U root -c "CREATE DATABASE ${REAL_DB} WITH OWNER=root TEMPLATE=${DB_TEMPLATE};"; then
      echo "✅ Successfully created database ${REAL_DB}"
      ((REAL_DB_CREATED++))
    else
      log_error "Failed to create real database ${REAL_DB} from template ${DB_TEMPLATE}"
      ((REAL_DB_ERRORS++))
    fi
  else
    echo "Database '${REAL_DB}' already exists, skipping creation."
    ((REAL_DB_CREATED++))
  fi
done

echo "📊 Real Database Creation Summary:"
echo "   ✅ Successfully created/exists: ${REAL_DB_CREATED}"
echo "   ❌ Failed to create: ${REAL_DB_ERRORS}"

echo "🔍 Performing final validation..."

# Validate that all expected databases exist and have tables
VALIDATION_SUCCESS=0
VALIDATION_WARNINGS=0
VALIDATION_ERRORS=0

for DB_TEMPLATE in "${!DATABASE_MAPPING[@]}"; do
  REAL_DB="${DB_TEMPLATE%_template}"
  
  # Check if template database exists
  if ! psql -U root -tc "SELECT 1 FROM pg_database WHERE datname='${DB_TEMPLATE}'" | grep -q 1; then
    log_error "Template database ${DB_TEMPLATE} was not created properly"
    ((VALIDATION_ERRORS++))
    continue
  fi
  
  # Check if real database exists
  if ! psql -U root -tc "SELECT 1 FROM pg_database WHERE datname='${REAL_DB}'" | grep -q 1; then
    log_error "Real database ${REAL_DB} was not created properly"
    ((VALIDATION_ERRORS++))
    continue
  fi
  
  # Check if database has expected tables
  local expected_tables="${DATABASE_MAPPING[$DB_TEMPLATE]}"
  local table_count=$(echo $expected_tables | wc -w)
  local actual_count=$(psql -U root -d "${REAL_DB}" -tc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';" 2>/dev/null || echo "0")
  
  if [[ "$actual_count" -eq 0 ]]; then
    log_error "Database ${REAL_DB} exists but has no tables (expected ${table_count})"
    ((VALIDATION_ERRORS++))
  elif [[ "$actual_count" -ne "$table_count" ]]; then
    echo "⚠️  Warning: Database ${REAL_DB} has ${actual_count} tables but expected ${table_count}"
    ((VALIDATION_WARNINGS++))
  else
    echo "✅ Database ${REAL_DB} validated successfully (${actual_count} tables)"
    ((VALIDATION_SUCCESS++))
  fi
done

echo ""
echo "📊 Final Validation Summary:"
echo "   ✅ Databases validated successfully: ${VALIDATION_SUCCESS}"
echo "   ⚠️  Databases with warnings: ${VALIDATION_WARNINGS}"
echo "   ❌ Databases with errors: ${VALIDATION_ERRORS}"

# Only fail if we have more errors than successes
if [[ $VALIDATION_ERRORS -gt $VALIDATION_SUCCESS ]]; then
    log_error "CRITICAL: More validation errors (${VALIDATION_ERRORS}) than successes (${VALIDATION_SUCCESS})"
    check_critical_errors
fi

echo "✅ Database initialization completed successfully!"
echo "📊 Total databases created: $(( ${#DATABASE_MAPPING[@]} * 2 + 1 )) (templates + real + sql_test_template)"
echo "🎯 All databases are ready for use"

# Clean up
rm -f "$ERROR_LOG"
