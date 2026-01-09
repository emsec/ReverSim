from datetime import datetime
from enum import StrEnum

from app.model.LogEvents import LogEvent


type TIMESTAMP_MS = datetime


class LogValidationError(RuntimeError):

	def __init__(self, message: str, event: LogEvent|None = None) -> None:
		super().__init__(message)
		self.event = event


class CurrentState(StrEnum):
	LOADED = 'Loaded'
	STARTED = 'In Progress'
	FINISHED = 'Finished'


class CurrentLevelState(StrEnum):
	LOADED = 'Loaded'
	STARTED = 'In Progress'
	SOLVED = 'Solved'
	FINISHED = 'Finished'
	SKIPPED = 'Skipped'
