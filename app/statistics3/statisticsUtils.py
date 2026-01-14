from datetime import datetime
from enum import StrEnum

from app.model.LogEvents import LogEvent

type TIMESTAMP_MS = datetime

TIME_TOLERANCE = 0.1 # seconds


class LogValidationError(RuntimeError):

	def __init__(self, message: str, event: LogEvent|None = None) -> None:
		"""
		A LogValidationError is thrown whenever something in the player event logs seems
		implausible, e.g. a switch click in a level without switches.
		
		:param message: Description
		:param event: Description
		"""
		super().__init__(message)
		self.event = event


class CurrentState(StrEnum):
	LOADED = 'Loaded'
	STARTED = 'In Progress'
	FINISHED = 'Finished'
	TIMEOUT = 'Timeout'


class CurrentLevelState(StrEnum):
	LOADED = 'Loaded'
	STARTED = 'In Progress'
	SOLVED = 'Solved'
	FINISHED = 'Finished'
	SKIPPED = 'Skipped'
	TIMEOUT = 'Timeout'
