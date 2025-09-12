# db_utils.py
import subprocess
import psycopg2
from psycopg2 import OperationalError
from psycopg2.pool import SimpleConnectionPool
from logger import log_section_header, log_section_footer, PrintLogger
import time
import sys
import json
import re
import os, csv

_postgresql_pools = {}

DEFAULT_DB_CONFIG = {
    "minconn": 3,
    "maxconn": 10,
    "user": "root",
    "password": "123123",
    "host": "localhost",
    "port": 5432,
}


def _get_or_init_pool(db_name):
    """
    Returns a connection pool for the given database name, creating one if it does not exist.
    """
    if db_name not in _postgresql_pools:
        config = DEFAULT_DB_CONFIG.copy()
        config.update({"dbname": db_name})
        _postgresql_pools[db_name] = SimpleConnectionPool(
            config["minconn"],
            config["maxconn"],
            dbname=config["dbname"],
            user=config["user"],
            password=config["password"],
            host=config["host"],
            port=config["port"],
        )
    return _postgresql_pools[db_name]


def perform_query_on_postgresql_databases(query, db_name, conn=None):
    """
    Executes the given query on the specified database, returns (result, conn).
    Automatically commits if the query is recognized as a write operation.
    """
    MAX_ROWS = 10000
    pool = _get_or_init_pool(db_name)
    need_to_put_back = False

    if conn is None:
        conn = pool.getconn()
        need_to_put_back = True

    cursor = conn.cursor()

    upper_query = query.upper()
    if "WITH RECURSIVE" in upper_query:
        try:
            cursor.execute("SET max_recursive_iterations = 100;")
            cursor.execute("SET statement_timeout = '15s';")
        except Exception as e:
            conn.rollback()
            cursor.execute("SET statement_timeout = '15s';")
    else:
        cursor.execute("SET statement_timeout = '60s';")  # 标准查询超时

    try:
        cursor.execute(query)
        lower_q = query.strip().lower()
        conn.commit()

        if lower_q.startswith("select") or lower_q.startswith("with"):
            # Fetch up to MAX_ROWS + 1 to see if there's an overflow
            rows = cursor.fetchmany(MAX_ROWS + 1)
            if len(rows) > MAX_ROWS:
                rows = rows[:MAX_ROWS]
            result = rows
        else:
            try:
                result = cursor.fetchall()
            except psycopg2.ProgrammingError:
                result = None

        return (result, conn)

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        try:
            cursor.execute("SET statement_timeout = '60s';")
            if "WITH RECURSIVE" in upper_query:
                # cursor.execute("RESET max_recursive_iterations;")
                pass
        except:
            pass
        cursor.close()
        if need_to_put_back:
            pass


def close_postgresql_connection(db_name, conn):
    """
    Release a connection back to the pool when you are done with it.
    """
    if db_name in _postgresql_pools:
        pool = _postgresql_pools[db_name]
        pool.putconn(conn)


def close_all_postgresql_pools():
    """
    Closes all connections in all pools (e.g., at application shutdown).
    """
    for pool in _postgresql_pools.values():
        pool.closeall()
    _postgresql_pools.clear()


def close_all_postgresql_pools():
    """
    Close all connection pools and clear the pools dictionary.
    """
    for db_name in list(_postgresql_pools.keys()):
        close_postgresql_pool(db_name)
    _postgresql_pools.clear()


def diagnose_database_connectivity(pg_password, logger=None):
    """
    Diagnose database connectivity and list available databases and templates.
    """
    if logger is None:
        logger = PrintLogger()
        
    pg_host = "localhost"
    pg_port = 5432
    pg_user = "root"
    
    env_vars = os.environ.copy()
    env_vars["PGPASSWORD"] = pg_password
    
    logger.info("=== Database Connectivity Diagnosis ===")
    
    try:
        # Test basic connectivity
        test_command = [
            "psql",
            "-h",
            pg_host,
            "-p",
            str(pg_port),
            "-U",
            pg_user,
            "-d",
            "postgres",
            "-c",
            "SELECT version();",
        ]
        result = subprocess.run(
            test_command,
            check=True,
            env=env_vars,
            timeout=30,
            capture_output=True,
            text=True,
        )
        logger.info("✓ Database connectivity successful")
        
        # List all databases
        list_all_dbs_command = [
            "psql",
            "-h",
            pg_host,
            "-p",
            str(pg_port),
            "-U",
            pg_user,
            "-d",
            "postgres",
            "-t",
            "-c",
            "SELECT datname, datistemplate FROM pg_database ORDER BY datname;",
        ]
        db_result = subprocess.run(
            list_all_dbs_command,
            check=True,
            env=env_vars,
            timeout=30,
            capture_output=True,
            text=True,
        )
        
        logger.info("Available databases:")
        for line in db_result.stdout.split('\n'):
            if line.strip():
                parts = line.strip().split('|')
                if len(parts) >= 2:
                    db_name = parts[0].strip()
                    is_template = parts[1].strip()
                    logger.info(f"  - {db_name} (template: {is_template})")
        
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"✗ Database connectivity failed: {e}")
        logger.error(f"Command stderr: {e.stderr if hasattr(e, 'stderr') else 'N/A'}")
        return False
    except Exception as e:
        logger.error(f"✗ Unexpected error during connectivity test: {e}")
        return False


def close_postgresql_pool(db_name):
    """
    Close the pool for a specific db_name and remove its reference.
    """
    if db_name in _postgresql_pools:
        pool = _postgresql_pools.pop(db_name)
        pool.closeall()


def get_connection_for_phase(db_name, logger=None):
    """
    Acquire a new connection (borrowed from the connection pool) for a specific phase.
    """
    if logger is None:
        logger = PrintLogger()
        
    logger.info(f"Acquiring dedicated connection for phase on db: {db_name}")
    result, conn = perform_query_on_postgresql_databases("SELECT 1", db_name, conn=None)
    return conn


def reset_and_restore_database(db_name, pg_password, logger=None):
    """
    Resets the database by dropping it and re-creating it from its template.
    1) close pool
    2) terminate connections
    3) dropdb
    4) createdb --template ...
    """
    if logger is None:
        logger = PrintLogger()

    pg_host = "localhost"
    pg_port = 5432
    pg_user = "root"

    env_vars = os.environ.copy()
    env_vars["PGPASSWORD"] = pg_password
    base_db_name = db_name.split("_process_")[0]
    template_db_name = f"{base_db_name}_template"

    print(f"Resetting database {db_name} using template {template_db_name}")
    logger.info(f"Starting database reset: {db_name} -> {template_db_name}")
    
    # First, let's check database connectivity and list available databases for debugging
    try:
        list_dbs_command = [
            "psql",
            "-h",
            pg_host,
            "-p",
            str(pg_port),
            "-U",
            pg_user,
            "-d",
            "postgres",
            "-t",
            "-c",
            "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname;",
        ]
        db_list_result = subprocess.run(
            list_dbs_command,
            check=False,
            env=env_vars,
            timeout=30,
            capture_output=True,
            text=True,
        )
        if db_list_result.returncode == 0:
            available_dbs = [db.strip() for db in db_list_result.stdout.split('\n') if db.strip()]
            logger.info(f"Available databases: {available_dbs}")
        else:
            logger.warning(f"Could not list databases: {db_list_result.stderr}")
            
        # Also check template databases
        list_templates_command = [
            "psql",
            "-h",
            pg_host,
            "-p",
            str(pg_port),
            "-U",
            pg_user,
            "-d",
            "postgres",
            "-t",
            "-c",
            "SELECT datname FROM pg_database WHERE datistemplate = true AND datname LIKE '%_template' ORDER BY datname;",
        ]
        template_list_result = subprocess.run(
            list_templates_command,
            check=False,
            env=env_vars,
            timeout=30,
            capture_output=True,
            text=True,
        )
        if template_list_result.returncode == 0:
            available_templates = [db.strip() for db in template_list_result.stdout.split('\n') if db.strip()]
            logger.info(f"Available template databases: {available_templates}")
            if template_db_name not in available_templates:
                logger.warning(f"Template database {template_db_name} not found in available templates!")
        else:
            logger.warning(f"Could not list template databases: {template_list_result.stderr}")
    except Exception as e:
        logger.warning(f"Failed to check database connectivity: {e}")

    # 1) Close the pool
    print(f"Closing connection pool for database {db_name} before resetting.")
    close_postgresql_pool(db_name)

    print(f"Connection pool for database {db_name} closed.")
    # 2) Terminate existing connections (best effort, don't fail if this doesn't work)
    try:
        terminate_command = [
            "psql",
            "-h",
            pg_host,
            "-p",
            str(pg_port),
            "-U",
            pg_user,
            "-d",
            "postgres",
            "-c",
            f"""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = '{db_name}' AND pid <> pg_backend_pid();
            """,
        ]
        result = subprocess.run(
            terminate_command,
            check=True,
            env=env_vars,
            timeout=60,
            capture_output=True,
            text=True,
        )
        logger.info(f"All connections to database {db_name} have been terminated.")
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to terminate connections to database {db_name}: {e}")
        logger.warning(f"Command stderr: {e.stderr if hasattr(e, 'stderr') else 'N/A'}")
        logger.info("Continuing with reset... (this is usually not critical)")
    except Exception as e:
        logger.warning(f"Unexpected error while terminating connections to database {db_name}: {e}. Continuing with reset...")

    # 3) dropdb (best effort, continue even if it fails)
    try:
        drop_command = [
            "dropdb",
            "--if-exists",
            "-h",
            pg_host,
            "-p",
            str(pg_port),
            "-U",
            pg_user,
            db_name,
        ]
        result = subprocess.run(
            drop_command,
            check=True,
            env=env_vars,
            timeout=60,
            capture_output=True,
            text=True,
        )
        logger.info(f"Database {db_name} dropped if it existed.")
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to drop database {db_name}: {e}")
        logger.warning(f"Command stderr: {e.stderr if hasattr(e, 'stderr') else 'N/A'}")
        logger.info("Continuing with recreation... (database might not have existed)")
    except Exception as e:
        logger.warning(f"Unexpected error while dropping database {db_name}: {e}. Continuing with recreation...")

    # 4) createdb --template=xxx_template
    try:
        # First, let's verify the template database exists
        check_template_command = [
            "psql",
            "-h",
            pg_host,
            "-p",
            str(pg_port),
            "-U",
            pg_user,
            "-d",
            "postgres",
            "-t",
            "-c",
            f"SELECT 1 FROM pg_database WHERE datname = '{template_db_name}';",
        ]
        template_check = subprocess.run(
            check_template_command,
            check=False,
            env=env_vars,
            timeout=30,
            capture_output=True,
            text=True,
        )
        
        if template_check.returncode != 0 or not template_check.stdout.strip():
            error_msg = f"Template database {template_db_name} does not exist or is not accessible"
            logger.error(error_msg)
            logger.error(f"Template check stderr: {template_check.stderr}")
            raise Exception(error_msg)
        
        logger.info(f"Template database {template_db_name} verified as existing")
        
        create_command = [
            "createdb",
            "-h",
            pg_host,
            "-p",
            str(pg_port),
            "-U",
            pg_user,
            db_name,
            "--template",
            template_db_name,
        ]
        result = subprocess.run(
            create_command,
            check=True,
            env=env_vars,
            timeout=60,
            capture_output=True,
            text=True,
        )
        logger.info(
            f"Database {db_name} created from template {template_db_name} successfully."
        )
    except subprocess.CalledProcessError as e:
        error_msg = f"Failed to create database {db_name} from template {template_db_name}: {e}"
        logger.error(error_msg)
        logger.error(f"Command stderr: {e.stderr if hasattr(e, 'stderr') else 'N/A'}")
        raise Exception(error_msg)
    except Exception as e:
        error_msg = f"Unexpected error while creating database {db_name} from template {template_db_name}: {e}"
        logger.error(error_msg)
        raise Exception(error_msg)


def create_ephemeral_db_copies(
    base_db_names, num_copies, pg_password, logger, max_retries=3
):
    pg_host = "localhost"
    pg_port = 5432
    pg_user = "root"
    env_vars = os.environ.copy()
    env_vars["PGPASSWORD"] = pg_password

    ephemeral_db_pool = {}

    for base_db in base_db_names:
        base_template = f"{base_db}_template"
        ephemeral_db_pool[base_db] = []
        logger.info(f"Processing database: {base_db}, template: {base_template}")

        for i in range(1, num_copies + 1):
            ephemeral_name = f"{base_db}_process_{i}"
            success = False

            for attempt in range(max_retries):
                try:
                    logger.info(
                        f"Attempt {attempt+1}/{max_retries}: Dropping existing db {ephemeral_name} if exists"
                    )
                    drop_cmd = [
                        "dropdb",
                        "--if-exists",
                        "-h",
                        pg_host,
                        "-p",
                        str(pg_port),
                        "-U",
                        pg_user,
                        ephemeral_name,
                    ]
                    subprocess.run(
                        drop_cmd,
                        check=False,
                        env=env_vars,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=30,
                    )

                    logger.info(
                        f"Attempt {attempt+1}/{max_retries}: Creating ephemeral db {ephemeral_name} from {base_template}"
                    )
                    create_cmd = [
                        "createdb",
                        "-h",
                        pg_host,
                        "-p",
                        str(pg_port),
                        "-U",
                        pg_user,
                        ephemeral_name,
                        "--template",
                        base_template,
                    ]
                    subprocess.run(
                        create_cmd,
                        check=True,
                        env=env_vars,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=60,
                    )

                    success = True
                    logger.info(f"Successfully created ephemeral db: {ephemeral_name}")
                    break

                except subprocess.SubprocessError as e:
                    logger.error(f"Attempt {attempt+1}/{max_retries} failed: {e}")
                    if attempt == max_retries - 1:
                        logger.error(
                            f"Failed to create {ephemeral_name} after {max_retries} attempts"
                        )
                    else:
                        logger.info(f"Waiting before retry...")
                        time.sleep(5)
            if success:
                ephemeral_db_pool[base_db].append(ephemeral_name)

        if not ephemeral_db_pool[base_db]:
            logger.warning(
                f"No ephemeral copies could be created for {base_db}, will skip items using this database"
            )
        else:
            logger.info(
                f"For base_db={base_db}, ephemeral db list = {ephemeral_db_pool[base_db]}"
            )

    return ephemeral_db_pool


def drop_ephemeral_dbs(ephemeral_db_pool_dict, pg_password, logger):
    """
    Delete all ephemeral databases created during the script execution.
    """
    pg_host = "localhost"
    pg_port = 5432
    pg_user = "root"
    env_vars = os.environ.copy()
    env_vars["PGPASSWORD"] = pg_password

    logger.info("=== Cleaning up ephemeral databases ===")
    for base_db, ephemeral_list in ephemeral_db_pool_dict.items():
        for ephemeral_db in ephemeral_list:
            logger.info(f"Dropping ephemeral db: {ephemeral_db}")
            drop_cmd = [
                "dropdb",
                "--if-exists",
                "-h",
                pg_host,
                "-p",
                str(pg_port),
                "-U",
                pg_user,
                ephemeral_db,
            ]
            try:
                subprocess.run(
                    drop_cmd,
                    check=True,
                    env=env_vars,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to drop ephemeral db {ephemeral_db}: {e}")


def execute_queries(queries, db_name, conn, logger=None, section_title=""):
    """
    Execute a list of queries using the SAME connection (conn).
    Returns (query_result, execution_error_flag, timeout_flag).
    Once the first error occurs, we break out and return immediately.
    """
    if logger is None:
        logger = PrintLogger()

    log_section_header(section_title, logger)
    query_result = None
    execution_error = False
    timeout_error = False

    for i, query in enumerate(queries):
        try:
            logger.info(f"Executing query {i+1}/{len(queries)}: {query}")
            query_result, conn = perform_query_on_postgresql_databases(
                query, db_name, conn=conn
            )
            # logger.info(f"Query result: {query_result}")

        except psycopg2.errors.QueryCanceled as e:
            # Timeout error
            logger.error(f"Timeout error executing query {i+1}: {e}")
            timeout_error = True
            break

        except OperationalError as e:
            # Operational errors (e.g., server not available, etc.)
            logger.error(f"OperationalError executing query {i+1}: {e}")
            execution_error = True
            break

        except psycopg2.Error as e:
            # Other psycopg2 errors (e.g., syntax errors, constraint violations)
            logger.error(f"psycopg2 Error executing query {i+1}: {e}")
            execution_error = True
            break

        except Exception as e:
            # Any other generic error
            logger.error(f"Generic error executing query {i+1}: {e}")
            execution_error = True
            break

        finally:
            logger.info(f"[{section_title}] DB: {db_name}, conn info: {conn}")

        # If an error is flagged, don't continue subsequent queries
        if execution_error or timeout_error:
            break

    log_section_footer(logger)
    return query_result, execution_error, timeout_error


def load_jsonl(file_path):
    """
    Loads JSONL data from file_path and returns a list of dicts.
    """
    try:
        with open(file_path, "r") as file:
            return [json.loads(line) for line in file]
    except Exception as e:
        print(f"Failed to load JSONL file: {e}")
        sys.exit(1)


def split_field(data, field_name):
    """
    Retrieve the specified field from the data dictionary and split it based on [split].
    Returns a list of statements.
    """
    field_value = data.get(field_name, "")
    if not field_value:
        return []
    if isinstance(field_value, str):
        # Use [split] as the delimiter with optional surrounding whitespace
        sql_statements = [
            stmt.strip()
            for stmt in re.split(r"\[split\]\s*", field_value)
            if stmt.strip()
        ]
        return sql_statements
    elif isinstance(field_value, list):
        return field_value
    else:
        return []


def save_report_and_status(
    report_file_path,
    question_test_case_results,
    data_list,
    number_of_execution_errors,
    number_of_timeouts,
    number_of_assertion_errors,
    overall_accuracy,
    timestamp,
    big_logger,
):
    """
    Writes a report to report_file_path and updates the 'status'/'error_message' fields
    in data_list based on question_test_case_results.
    """
    total_instances = len(data_list)
    try:
        with open(report_file_path, "w") as report_file:
            report_file.write("--------------------------------------------------\n")
            report_file.write(
                "BIRD CRITIC Stack Overflow Result Statistics (Postgres, Multi-Thread):\n"
            )
            report_file.write(f"Number of Instances: {total_instances}\n")
            report_file.write(
                f"Number of Execution Errors: {number_of_execution_errors}\n"
            )
            report_file.write(f"Number of Timeouts: {number_of_timeouts}\n")
            report_file.write(
                f"Number of Assertion Errors: {number_of_assertion_errors}\n"
            )
            total_errors = (
                number_of_execution_errors
                + number_of_timeouts
                + number_of_assertion_errors
            )
            report_file.write(f"Total Errors: {total_errors}\n")
            report_file.write(f"Overall Accuracy: {overall_accuracy:.2f}%\n")
            report_file.write(f"Timestamp: {timestamp}\n\n")

            # Go through each question result
            for i, q_res in enumerate(question_test_case_results):
                q_idx = q_res["instance_id"]
                t_total = q_res["total_test_cases"]
                t_pass = q_res["passed_test_cases"]
                t_fail = t_total - t_pass
                failed_list_str = (
                    ", ".join(q_res["failed_test_cases"]) if t_fail > 0 else "None"
                )

                eval_phase_note = ""
                if q_res.get("evaluation_phase_execution_error"):
                    eval_phase_note += " | Eval Phase: Execution Error"
                if q_res.get("evaluation_phase_timeout_error"):
                    eval_phase_note += " | Eval Phase: Timeout Error"
                if q_res.get("evaluation_phase_assertion_error"):
                    eval_phase_note += " | Eval Phase: Assertion Error"

                report_file.write(
                    f"Question_{q_idx}: ({t_pass}/{t_total}) test cases passed, "
                    f"failed test cases: {failed_list_str}{eval_phase_note}\n"
                )

                # Update data_list with statuses
                if t_fail == 0:
                    # All testcases passed, no error-phase surprises
                    data_list[i]["status"] = "success"
                    data_list[i]["error_message"] = None
                else:
                    data_list[i]["status"] = "failed"
                    if failed_list_str != "None":
                        data_list[i]["error_message"] = f"{failed_list_str} failed"
                    else:
                        data_list[i]["error_message"] = eval_phase_note
    except Exception as e:
        big_logger.error(f"Failed to write report: {e}")


def generate_category_report(
    question_test_case_results,
    data_list,
    category_report_file,
    big_logger,
    model_name="",
    metric_name="Test Case",
):
    """
    Generates a report (txt file) summarizing success ratios across categories
    with the style

    Assumes each data_list[i] has a 'category' field: one of ["Query", "Efficiency", "Management", "Personalization"].
    Missing/invalid category defaults to "Personalization".
    """
    # Define recognized categories in a certain order
    levels = ["Query", "Management", "Personalization", "Efficiency", "Total"]
    # We'll keep track of counts and successes
    counts_dict = {
        "Query": 0,
        "Efficiency": 0,
        "Management": 0,
        "Personalization": 0,
        "Total": 0,
    }
    success_dict = {
        "Query": 0,
        "Efficiency": 0,
        "Management": 0,
        "Personalization": 0,
        "Total": 0,
    }

    # Tally up from results
    for i, q_res in enumerate(question_test_case_results):
        # Extract category from data_list; default to "Personalization" if missing or invalid.
        category = data_list[i].get("category", "Personalization")
        if category not in ["Query", "Efficiency", "Management", "Personalization"]:
            category = "Personalization"
        counts_dict[category] += 1
        counts_dict["Total"] += 1
        if q_res.get("status") == "success":
            success_dict[category] += 1
            success_dict["Total"] += 1

    # Prepare lists for printing in the style:
    # The "count" row
    count_list = [
        counts_dict["Query"],
        counts_dict["Management"],
        counts_dict["Personalization"],
        counts_dict["Efficiency"],
        counts_dict["Total"],
    ]

    # The "accuracy" row (if count == 0, ratio is 0.0)
    def ratio(success, total):
        return (success / total * 100) if total != 0 else 0.0

    score_list = [
        ratio(success_dict["Query"], counts_dict["Query"]),
        ratio(success_dict["Management"], counts_dict["Management"]),
        ratio(success_dict["Personalization"], counts_dict["Personalization"]),
        ratio(success_dict["Efficiency"], counts_dict["Efficiency"]),
        ratio(success_dict["Total"], counts_dict["Total"]),
    ]

    # Now let's write out the lines
    try:
        with open(category_report_file, "a") as rep_file:
            # Print the header (blank space + 5 levels)
            rep_file.write("{:20} {:20} {:20} {:20} {:20} {:20}\n".format("", *levels))
            # Print the count row
            rep_file.write(
                "{:20} {:<20} {:<20} {:<20} {:<20} {:<20}\n".format(
                    "count", *count_list
                )
            )
            # Separator line with metric name in the middle
            rep_file.write(
                f"===============================================    {metric_name}    ===============================================\n"
            )
            # Print the accuracy row with 2 decimals
            rep_file.write(
                "{:20} {:<20.2f} {:<20.2f} {:<20.2f} {:<20.2f} {:<20.2f}\n".format(
                    "", *score_list
                )
            )
            rep_file.write(
                "================================================================================================================\n"
            )
        big_logger.info(f"Saved category report to {category_report_file}")
    except Exception as e:
        big_logger.error(f"Failed to write category report: {e}")
    csv_path = "/app/data/postgresql.csv"
    file_exists = os.path.exists(csv_path)
    try:
        with open(csv_path, "a", newline="") as csvfile:
            writer = csv.writer(csvfile)
            # If the file does not exist, create it and write the header.
            if not file_exists:
                writer.writerow(
                    [
                        "Model",
                        "Query",
                        "Management",
                        "Personalization",
                        "Efficiency",
                        "Total",
                    ]
                )
            # Write the current record.
            writer.writerow(
                [
                    model_name,
                    score_list[0],
                    score_list[1],
                    score_list[2],
                    score_list[3],
                    score_list[4],
                ]
            )
        big_logger.info(f"Saved CSV record to {csv_path}")
    except Exception as e:
        big_logger.error(f"Failed to write CSV record: {e}")
