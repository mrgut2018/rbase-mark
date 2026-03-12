"""
MySQL connection management module.

This module provides functions for managing MySQL database connections.
"""

import threading

import pymysql
from pymysql.connections import Connection

# Thread-local storage for database connections (each thread gets its own connection)
_thread_local = threading.local()


def _create_connection(rbase_db_config: dict) -> Connection:
    """Create a new MySQL connection from config."""
    return pymysql.connect(
        host=rbase_db_config.get("config", {}).get("host", "localhost"),
        port=int(rbase_db_config.get("config", {}).get("port", 3306)),
        user=rbase_db_config.get("config", {}).get("username", ""),
        password=rbase_db_config.get("config", {}).get("password", ""),
        database=rbase_db_config.get("config", {}).get("database", ""),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def get_mysql_connection(rbase_db_config: dict) -> Connection:
    """
    Get MySQL database connection, prioritizing reuse of existing active connection.

    Each thread maintains its own connection via thread-local storage,
    making this function safe to use in multi-threaded contexts.

    Args:
        rbase_db_config: Database configuration dictionary

    Returns:
        MySQL database connection object

    Raises:
        ValueError: If the database provider is not MySQL
        ConnectionError: If connection to database fails
    """
    # Check database provider
    if rbase_db_config.get("provider", "").lower() != "mysql":
        raise ValueError("Currently only MySQL database is supported")

    # Try to reuse existing thread-local connection
    conn = getattr(_thread_local, "connection", None)
    if conn is not None:
        try:
            conn.ping(reconnect=True)
            return conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            _thread_local.connection = None

    # Create a new connection for this thread
    try:
        conn = _create_connection(rbase_db_config)
        _thread_local.connection = conn
        return conn
    except Exception as e:
        raise ConnectionError(f"Failed to connect to MySQL database: {e}")


def close_mysql_connection():
    """
    Close the current thread's active MySQL connection.
    """
    conn = getattr(_thread_local, "connection", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        finally:
            _thread_local.connection = None
