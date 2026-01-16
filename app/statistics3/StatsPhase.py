
from dataclasses import dataclass
import logging
from datetime import timedelta

from app.statistics3.statisticsUtils import (
	TIME_TOLERANCE,
	TIMESTAMP_MS,
	CurrentState,
	LogValidationError,
)
from app.utilsGame import PhaseType

@dataclass
class StatsPhase:
	phaseType: PhaseType
	time_load: TIMESTAMP_MS

	time_start: TIMESTAMP_MS|None = None
	time_start_levels: TIMESTAMP_MS|None = None
	time_finish: TIMESTAMP_MS|None = None

	time_limit: timedelta|None = None

	status: CurrentState = CurrentState.LOADED
	reloaded = False


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


	def start_phase_time_limit(self, time_start_levels: TIMESTAMP_MS):
		self.time_start_levels = time_start_levels

		if self.status not in [CurrentState.LOADED, CurrentState.STARTED]:
			raise LogValidationError(f'Expected phase loaded, got {self.status}')

		if self.time_start is not None and self.time_start > time_start_levels:
			raise LogValidationError('The time_start_levels is invalid')


	def stop_phase_time_limit(self, time_stop_levels: TIMESTAMP_MS):
		if self.status != CurrentState.STARTED:
			raise LogValidationError(f'Expected phase started, got {self.status}')
		
		self.finish(time_stop_levels)
		self.status = CurrentState.TIMEOUT
