import logging
import os
import sqlite3
import uuid
from typing import Any, Optional

from flask import Flask
from flask_alembic import Alembic
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import QueuePool

from app.utilsGame import safe_join

# WAL doesn't really make sense since we want our database to be a single file. But the
# option is there
ENABLE_WAL = False

# Enable the pysqlite dirty fixes. You might need to disable them to generate a new
# Alembic revision/release
SQLITE_HACKS = True


class Base(DeclarativeBase):
	"""Base Model that all Model classes that should be persisted have to extend."""
	pass


# Some default options added to the gameServer.py@DefaultFlaskSettings
_sqlalchemy_args: dict[str, Any] = {
	"model_class": Base,
	"engine_options": {
		# NullPool is more robust against wsgi server implementations, that use multiprocessing / os.fork
		# https://docs.sqlalchemy.org/en/20/core/pooling.html#using-connection-pools-with-multiprocessing-or-os-fork
		# But it comes with a performance penalty, therefore we use the static pool and have to make sure,
		# that a connection is not forked to the child process.
		"poolclass": QueuePool
	}
}

if SQLITE_HACKS:
	_sqlalchemy_args["engine_options"]["connect_args"] = {
		# https://docs.python.org/3.12/library/sqlite3.html#transaction-control
		"autocommit": sqlite3.LEGACY_TRANSACTION_CONTROL
		#"isolation_level": "EXCLUSIVE" # EXCLUSIVE 
	}


# Init the DB
db: SQLAlchemy = SQLAlchemy(**_sqlalchemy_args)

_app: Optional[Flask] = None
_alembic: Optional[Alembic] = None


class ReverSimDatabase:

	_alembic: Alembic | None = None
	sqlite_hacks_enabled = False

	@classmethod
	def createDatabase(cls, app: Flask):
		global _alembic, _app
		_app = app

		try:
			# Ensure that the folder for the database exists
			folder_database = safe_join(app.instance_path, "statistics")
			os.makedirs(folder_database, exist_ok=True)

			# Check that we have write permissions in the folder/volume
			test_if_folder_is_writable_file = folder_database + "/test_writable.txt"
			with open(test_if_folder_is_writable_file, 'tw') as f:
				f.write("Hello World!")
			
			# Get rid of the temporary file
			os.remove(test_if_folder_is_writable_file)

		except Exception:
			logging.exception("Unable to create folder for database!")

		db.init_app(app)

		try:
			_alembic = Alembic()
			_alembic.init_app(app)
		except Exception:
			logging.exception("Alembic init failed: ")

		# Create or upgrade the database
		with app.app_context():
			event.listen(db.engine, "checkout", cls.checkout)
			ReverSimDatabase.enableSQLiteHacks()
			db.create_all()

			# Exit the app if the version is outdated
			cls.check()


	@staticmethod
	def do_connect(dbapi_connection: DBAPIConnection, connection_record: Any):
		connection_record.info["pid"] = os.getpid()

		if SQLITE_HACKS:
			# disable pysqlite's emitting of the BEGIN statement entirely.
			# also stops it from emitting COMMIT before any DDL.
			dbapi_connection.isolation_level = None # type: ignore


	@staticmethod
	def do_begin(conn: Any):
		if SQLITE_HACKS:
			assert conn.connection.dbapi_connection.isolation_level is None, \
					"Expected the isolation_level to be None, since we are manually emitting our begin" # type: ignore

			# emit our own BEGIN
			# NOTE: When not in EXCLUSIVE mode, a transaction can later be upgraded to a
			# write, in which case multiple reads are no longer possible as the other 
			# transaction might have performed a dirty read and the ACID principle would
			# be violated. This is probably the reason, why this will not timeout other
			# transactions but instead immediately throws an SQLITE_BUSY error.
			conn.exec_driver_sql("BEGIN EXCLUSIVE")


	@staticmethod
	def checkout(dbapi_connection: Any, connection_record: Any, connection_proxy: Any):
		assert connection_record.info["pid"] == os.getpid(), "pid mismatch, this connection belongs to a different process!"


	@classmethod
	def check(cls):
		"""Check if the database is up to date ~~and exit the application otherwise~~"""

		global _alembic
		if _alembic is None:
			logging.critical('-------------------------------------------------')
			logging.critical(" Flask-Alembic should be initialized at this point!!!")
			logging.critical(" Without Alembic we have to skip the database version check!")
			logging.critical('-------------------------------------------------')
			return "v?error"
		
		currentVersion = None
		latestVersion = None

		try:
			currentVersion = _alembic.current()
			latestVersion = _alembic.heads()
			assert len(currentVersion) <= 1, "ReverSim does not support Alembic upgrade branches yet"
			assert len(latestVersion) <= 1, "ReverSim does not support Alembic upgrade branches yet"

			if len(currentVersion) < 1:
				logging.info("No Alembic version table found. The database was probably just created.")
				_alembic.stamp() # Assume that the database was created with the latest ReverSim Code
				return "v?"
			
			if len(latestVersion) < 1:
				logging.error("No Alembic upgrade files found. Please check your migrations/ directory.")
				return "v?"

			currentRevID = currentVersion[0].revision
			latestRevID = latestVersion[0].revision

			# If the current version does not match the latest version, we are out of date
			if currentRevID != latestRevID:
				logging.error('-------------------------------------------------')
				logging.error(f' The database is out of date: {currentRevID} -> {latestRevID}, "{latestVersion[0].doc}"!')
				logging.error(' Please read "doc/Database.md" to learn how you can upgrade!')
				logging.error('-------------------------------------------------')
			else:
				logging.info(f"Current Alembic DB version: {currentRevID}, {currentVersion[0].doc}.")

			return currentRevID

		except Exception as e:
			logging.exception(f'Alembic version detection failed: "{e}"')

		return "v?"


	@classmethod
	def enableSQLiteHacks(cls):
		"""The SQLite driver needs some special treatment to behave as expected.
		
		Further information:
		- https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#pysqlite-serializable
		- [doc/Database.md](doc/Database.md)
		"""
		if not SQLITE_HACKS or cls.sqlite_hacks_enabled:
			return

		logging.info("Enabling the SQLite modifications to ensure a working transactional scope")
		event.listen(db.engine, "connect", cls.do_connect)
		event.listen(db.engine, "begin", cls.do_begin)

		db.engine.dispose(close=False)

		with db.engine.connect() as connection:
			dbapi_connection = connection.connection.dbapi_connection
			assert dbapi_connection is not None, "Expecting an initialized dbapi_connection at this state..."
			assert dbapi_connection.autocommit == sqlite3.LEGACY_TRANSACTION_CONTROL, \
				("There is a long standing bug in the Pysqlite driver, which violates SQLites"
				"ability to enforce the ACID principles. While it is fixed in theory with "
				"Python 3.12, we still have to resort to the legacy transaction control, as"
				"there is no way with the new `autocommit=False` settings to enforce "
				"`BEGIN EXCLUSIVE`...")
			dbapi_connection.isolation_level = None # type: ignore
			
		cls.sqlite_hacks_enabled = True


	@classmethod
	def pre_db_connect(cls, dbapi_connection: DBAPIConnection, connection_record: Any):
		""""""
		# Turn on Write Ahead Logging
		if ENABLE_WAL:
			cursor = dbapi_connection.cursor()
			cursor.execute("PRAGMA journal_mode=WAL")
			cursor.close()


class SanityVersion:
	"""Add a version_id column to a db Model to fortify against race conditions.

	SQLAlchemy has a mechanism to detect in memory race conditions. Add this Mixin to 
	any class where a race might be devastating. However this cannot protect against all
	race conditions.
	
	https://docs.sqlalchemy.org/en/20/orm/versioning.html
	"""
	version_id: Mapped[int] = mapped_column(nullable=False)
	__mapper_args__ = { # type: ignore
		"version_id_col": version_id,
		"version_id_generator": lambda version: uuid.uuid4().hex, # type: ignore
	}


# Database specific config (especially max string lengths)
LEN_SESSION_ID = 8
LEN_GROUP = 64
LEN_PHASE = 16
LEN_LEVEL_PATH = LEN_GROUP
LEN_LEVEL_TYPE = 12
LEN_GIT_HASH_S = 16
LEN_VERSION = 12
LEN_LEVEL = 1024
