import logging
from datetime import timedelta

from app.statistics3.statisticsUtils import (
	TIME_TOLERANCE,
	TIMESTAMP_MS,
	CurrentLevelState,
	LogValidationError,
)
from app.utilsGame import LevelType


class StatsSlide:

	def __init__(self,
		type_slide: LevelType,
		log_name: str,
		time_load: TIMESTAMP_MS
	) -> None:
		self.slide_type = type_slide
		self.log_name = log_name

		self.time_load: TIMESTAMP_MS = time_load
		self.time_start: TIMESTAMP_MS|None = None
		self.time_finish: TIMESTAMP_MS|None = None

		self.time_limit: timedelta|None = None

		self.status: CurrentLevelState = CurrentLevelState.LOADED
		self.reloaded = False


	def start(self, time_start: TIMESTAMP_MS, time_limit: float|None):
		# Check the reload flag and clear it, dropping the first reload event
		if self.reloaded:
			self.reloaded = False
			return

		if self.status != CurrentLevelState.LOADED:
			raise LogValidationError(f'Cannot start {self.slide_type} with status {self.status}')

		self.status = CurrentLevelState.STARTED
		self.time_start = time_start

		# Only levels will send a per level time limit if configured
		if isinstance(time_limit, float) and time_limit > TIME_TOLERANCE:
			self.time_limit = timedelta(seconds=time_limit)
		else:
			self.time_limit = None


	def stop(self, time_finish: TIMESTAMP_MS):
		if self.status == CurrentLevelState.TIMEOUT:
			logging.debug('Stop after level timeouted')
			assert self.time_finish is not None
			return

		if self.status != CurrentLevelState.STARTED:
			raise LogValidationError(f'Cannot finish {self.slide_type} with status {self.status}')
		assert self.time_start is not None, "Started means timestamp should have been set"
		
		self.status = CurrentLevelState.FINISHED
		self.time_finish = time_finish

		# If the start event reported a time limit, check that it was adhered to
		if self.time_limit is not None:
			recorded_duration = self.time_finish - self.time_start
			allowed_duration = self.time_limit + timedelta(seconds=TIME_TOLERANCE)

			if recorded_duration > allowed_duration:
				logging.warning(f'Overtime {recorded_duration}, allowed was {allowed_duration} in {self.log_name}')
				#raise LogValidationError(f'Overtime {recorded_duration}, allowed was {allowed_duration}')


	def timeout(self, time_finish: TIMESTAMP_MS):
		self.stop(time_finish)
		self.status = CurrentLevelState.TIMEOUT


	def click_continue(self, time_finish: TIMESTAMP_MS):
		self.stop(time_finish)
