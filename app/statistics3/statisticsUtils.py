import dataclasses
from datetime import datetime, timedelta
from enum import StrEnum
import json
from typing import Any

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


class StatisticJSONEncoder(json.JSONEncoder):
	def default(self, o: Any):
		# Serialize StatsParticipant, StatsPhase etc.
		if dataclasses.is_dataclass(o):
			# type[dataclass] could theoretically slip through
			return dataclasses.asdict(o) # type: ignore
		
		# Serialize datetime objects in ISO 8601
		if isinstance(o, datetime):
			return o.isoformat()
		
		# Serialize timedelta as a float in seconds
		if isinstance(o, timedelta):
			return o.total_seconds()

		# Try the default handler
		return super().default(o)
