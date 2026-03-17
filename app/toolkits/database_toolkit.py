# database_toolkit.py - SQL database toolkit for Numel workflow nodes
# Usage: set ToolkitConfig name="database_toolkit", args={"url": "postgresql://user:${DB_PASS}@host/db"}
# Supports any SQLAlchemy-compatible URL: sqlite, postgresql, mysql, etc.

from typing import Any, Dict, List, Optional


class DatabaseToolkit:
	"""Toolkit for SQL database access via SQLAlchemy.
	Args: url (SQLAlchemy connection string, e.g. 'sqlite:///data.db',
	'postgresql://user:pass@host/db', 'mysql+pymysql://user:pass@host/db')."""

	__toolkit__ = True

	def __init__(self, url: str = "sqlite:///numel_data.db"):
		self._url    = url
		self._engine = None

	def _engine_(self):
		if self._engine is None:
			from sqlalchemy import create_engine
			self._engine = create_engine(self._url)
		return self._engine

	def query(self, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
		"""Run a SELECT query and return rows as a list of dicts.
		sql: SQL string (use :name placeholders for params);
		params: optional dict of parameter values.
		Returns list of row dicts."""
		from sqlalchemy import text
		with self._engine_().connect() as conn:
			result = conn.execute(text(sql), params or {})
			cols   = list(result.keys())
			return [dict(zip(cols, row)) for row in result.fetchall()]

	def execute(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
		"""Run an INSERT / UPDATE / DELETE statement.
		sql: SQL string (use :name placeholders for params);
		params: optional dict of parameter values.
		Returns {rowcount}."""
		from sqlalchemy import text
		with self._engine_().begin() as conn:
			result = conn.execute(text(sql), params or {})
			return {"rowcount": result.rowcount}

	def insert(self, table: str, row: Dict[str, Any]) -> Dict[str, Any]:
		"""Insert a single row into a table.
		table: table name; row: dict mapping column names to values.
		Returns {rowcount}."""
		from sqlalchemy import text
		cols         = ", ".join(row.keys())
		placeholders = ", ".join(f":{k}" for k in row.keys())
		sql          = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
		with self._engine_().begin() as conn:
			result = conn.execute(text(sql), row)
			return {"rowcount": result.rowcount}

	def list_tables(self) -> List[str]:
		"""Return a list of all table names in the database."""
		from sqlalchemy import inspect
		return inspect(self._engine_()).get_table_names()

	def describe_table(self, table: str) -> List[Dict[str, Any]]:
		"""Describe the columns of a table.
		table: table name.
		Returns list of {name, type, nullable} dicts."""
		from sqlalchemy import inspect
		cols = inspect(self._engine_()).get_columns(table)
		return [{"name": c["name"], "type": str(c["type"]), "nullable": c.get("nullable", True)} for c in cols]
