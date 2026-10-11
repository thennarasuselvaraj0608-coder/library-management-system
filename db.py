import os
import mysql.connector
from mysql.connector import Error

# Database connection configuration with sensible college defaults
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", "Mysql@123"),
    "database": os.environ.get("DB_NAME", "library_management_db"),
    "port": int(os.environ.get("DB_PORT", 3306)),
    "autocommit": False,
}


def get_db_connection():
    """
    Establishes and returns a connection to the MySQL database.
    Returns None if connection fails.
    """
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as error:
        print(f"[DATABASE ERROR] Connection failed: {error}")
        return None


def test_connection():
    """
    Tests if the database connection is healthy.
    Returns (True, message) or (False, error_message).
    """
    try:
        conn = get_db_connection()
        if conn and conn.is_connected():
            server_info = conn.server_info
            conn.close()
            return True, f"Connected to MySQL Server {server_info}"
        return False, "Unable to establish connection to database"
    except Exception as e:
        return False, str(e)


def execute_query(query, params=None, fetchone=False, fetchall=False, commit=False, dictionary=True):
    """
    Executes a parameterized SQL query safely.
    - Prevents SQL Injection via parameter binding (%s).
    - dictionary=True returns rows as dicts (e.g. row['title']) instead of tuples.
    - commit=True commits INSERT/UPDATE/DELETE statements.
    - Returns:
        - fetched row/rows if fetchone or fetchall is True
        - lastrowid if INSERT
        - affected rows count if UPDATE/DELETE
    """
    conn = get_db_connection()
    if conn is None:
        raise ConnectionError("Database connection could not be established.")

    cursor = None
    try:
        cursor = conn.cursor(dictionary=dictionary)
        cursor.execute(query, params or ())

        if commit:
            conn.commit()

        if fetchone:
            result = cursor.fetchone()
            return result
        elif fetchall:
            result = cursor.fetchall()
            return result

        # For INSERT, return new ID
        if cursor.lastrowid:
            return cursor.lastrowid
        # For UPDATE / DELETE, return affected rows
        return cursor.rowcount

    except Error as error:
        if conn and commit:
            try:
                conn.rollback()
            except Exception:
                pass
        print(f"[SQL ERROR] Query execution failed: {error}")
        print(f"[QUERY] {query} | PARAMS: {params}")
        raise error

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def execute_transaction(operations):
    """
    Executes a sequence of queries within a single ACID transaction block.
    Demonstrates DBMS Transaction Processing (Atomicity & Consistency).
    operations is a list of tuples: (query, params)
    """
    conn = get_db_connection()
    if conn is None:
        raise ConnectionError("Database connection could not be established.")

    cursor = None
    try:
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        results = []
        for query, params in operations:
            cursor.execute(query, params or ())
            results.append({
                "lastrowid": cursor.lastrowid,
                "rowcount": cursor.rowcount
            })

        conn.commit()
        return results

    except Error as error:
        conn.rollback()
        print(f"[TRANSACTION ERROR] Rolled back due to error: {error}")
        raise error

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def call_procedure(proc_name, params=None):
    """
    Calls a MySQL Stored Procedure safely.
    """
    conn = get_db_connection()
    if conn is None:
        raise ConnectionError("Database connection could not be established.")

    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.callproc(proc_name, params or ())
        conn.commit()
        
        # Fetch any returned results if available
        results = []
        for result in cursor.stored_results():
            results.extend(result.fetchall())
        return results
    except Error as error:
        conn.rollback()
        print(f"[PROCEDURE ERROR] Procedure {proc_name} failed: {error}")
        raise error
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
