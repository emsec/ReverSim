
from datetime import timedelta
import logging
from app.statistics3.statisticsUtils import TIME_TOLERANCE, TIMESTAMP_MS, CurrentState, LogValidationError
from app.utilsGame import PhaseType


class StatsPhase:

	def __init__(self, type_phase: PhaseType, time_load: TIMESTAMP_MS) -> None:
		self.phaseType = type_phase

		self.time_load: TIMESTAMP_MS = time_load
		self.time_start: TIMESTAMP_MS|None
		self.time_finish: TIMESTAMP_MS|None

		self.time_limit: timedelta|None = None

		self.status: CurrentState = CurrentState.LOADED
		self.reloaded = False


	def start(self, time_start: TIMESTAMP_MS, time_limit: float|None):
		# Check the reload flag and clear it, dropping the first reload event
		if self.reloaded:
			self.reloaded = False
			return

		if self.status != CurrentState.LOADED:
			raise LogValidationError(f'Cannot start {self.phaseType} with status {self.status}')

		self.status = CurrentState.STARTED
		self.time_start = time_start

		# Only levels will send a per level time limit if configured
		if isinstance(time_limit, float) and time_limit > TIME_TOLERANCE:
			self.time_limit = timedelta(seconds=time_limit)
		else:
			self.time_limit = None


	def finish(self, time_finish: TIMESTAMP_MS):
		if self.status != CurrentState.STARTED:
			raise LogValidationError(f'Cannot finish {self.phaseType} with status {self.status}')
		assert self.time_start is not None, "Started means timestamp should have been set"
		
		self.status = CurrentState.FINISHED
		self.time_finish = time_finish

		# If the start event reported a time limit, check that it was adhered to
		if self.time_limit is not None:
			recorded_duration = self.time_finish - self.time_start
			allowed_duration = self.time_limit + timedelta(seconds=TIME_TOLERANCE)

			if recorded_duration > allowed_duration:
				logging.warning(f'Overtime {recorded_duration}, allowed was {allowed_duration} in {self.phaseType}')
				#raise LogValidationError(f'Overtime {recorded_duration}, allowed was {allowed_duration}')
