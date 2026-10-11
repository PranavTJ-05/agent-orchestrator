from __future__ import annotations

import sqlite3
from typing import Any

from ..core.tool import Tool


class DatabaseTool(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="database",
            description="Execute SQL queries against a local SQLite database. Use this to create tables, insert data, query data, and manage database schemas.",
        )

    async def execute(
        self,
        action: str,
        db_path: str = "agent_data.db",
        table_name: str = "",
        sql: str = "",
        data: str = "",
        columns: str = "",
    ) -> str:
        """Execute a database operation.

        Args:
            action: One of: query, create_table, insert, list_tables, describe_table, drop_table
            db_path: Path to the SQLite database file (default: agent_data.db)
            table_name: Name of the table to operate on
            sql: Raw SQL query for 'query' action
            data: For 'insert' - a JSON string of records to insert (list of dicts)
            columns: For 'create_table' - JSON string of column definitions (list of {"name": ..., "type": ...})
        """
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row

            if action == "query":
                if not sql:
                    return "Error: 'sql' parameter is required for the query action."
                cursor = conn.execute(sql)
                rows = cursor.fetchall()
                if not rows:
                    return "Query returned no results."
                result = []
                for row in rows:
                    result.append(dict(row))
                import json
                return json.dumps(result, indent=2)

            elif action == "create_table":
                if not table_name or not columns:
                    return "Error: Both 'table_name' and 'columns' are required."
                import json as _json
                cols = _json.loads(columns)
                col_defs = [f"{c['name']} {c['type']}" for c in cols]
                sql_cmd = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(col_defs)})"
                conn.execute(sql_cmd)
                conn.commit()
                return f"Table '{table_name}' created successfully."

            elif action == "insert":
                if not table_name or not data:
                    return "Error: Both 'table_name' and 'data' are required."
                import json as _json
                records = _json.loads(data)
                if not records:
                    return "Error: Empty data array."
                if isinstance(records, dict):
                    records = [records]

                for record in records:
                    cols = ", ".join(record.keys())
                    placeholders = ", ".join(["?" for _ in record])
                    sql_cmd = f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})"
                    conn.execute(sql_cmd, list(record.values()))
                conn.commit()
                return f"Inserted {len(records)} record(s) into '{table_name}'."

            elif action == "list_tables":
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                tables = [row["name"] for row in cursor.fetchall()]
                if not tables:
                    return f"No tables found in database '{db_path}'."
                return f"Tables in {db_path}:\n" + "\n".join(f"  - {t}" for t in tables)

            elif action == "describe_table":
                if not table_name:
                    return "Error: 'table_name' is required."
                cursor = conn.execute(f"PRAGMA table_info({table_name})")
                columns_info = cursor.fetchall()
                if not columns_info:
                    return f"Table '{table_name}' not found."
                result = [f"Columns of '{table_name}':"]
                for col in columns_info:
                    nullable = "NULL" if col["notnull"] == 0 else "NOT NULL"
                    default = f" DEFAULT {col['dflt_value']}" if col["dflt_value"] else ""
                    pk = " PRIMARY KEY" if col["pk"] else ""
                    result.append(f"  - {col['name']} ({col['type']}, {nullable}{default}{pk})")
                return "\n".join(result)

            elif action == "drop_table":
                if not table_name:
                    return "Error: 'table_name' is required."
                conn.execute(f"DROP TABLE IF EXISTS {table_name}")
                conn.commit()
                return f"Table '{table_name}' dropped successfully."

            else:
                return f"Error: Unknown action '{action}'. Supported: query, create_table, insert, list_tables, describe_table, drop_table"

            conn.close()

        except Exception as e:
            return f"Error executing database action '{action}': {str(e)}"
