from typing import override
from app.statistics3.StatsSlide import StatsSlide
from app.statistics3.statisticsUtils import TIME_TOLERANCE, TIMESTAMP_MS, CurrentLevelState, LogValidationError
from app.utilsGame import LevelType


class StatsCircuit(StatsSlide):

	def __init__(self, type_slide: LevelType, log_name: str, time_load: TIMESTAMP_MS) -> None:
		super().__init__(type_slide, log_name, time_load)

		self.switchClicks: int = 0
		self.minSwitchClicks: int|None = None
		self.confirmClicks: int = 0


	def click_switch(self):
		if self.status != CurrentLevelState.STARTED:
			raise LogValidationError(f'Cannot click switch in {self.slide_type} with status {self.status}')
		
		self.switchClicks += 1


	def click_confirm(self, time_finish: TIMESTAMP_MS, solved: bool):
		# Confirm can only be clicked on an unsolved level, with the exception of the event
		# coming at the same time as the chrono stop event
		if self.status != CurrentLevelState.STARTED:
			assert self.time_finish is not None
			if (
				self.status not in [CurrentLevelState.FINISHED, CurrentLevelState.TIMEOUT] or 
				(time_finish - self.time_finish).total_seconds() > TIME_TOLERANCE
			):
				raise LogValidationError(f'Cannot click confirm in {self.slide_type} with status {self.status}')

		self.confirmClicks += 1


	@override
	def click_continue(self, time_finish: TIMESTAMP_MS):
		if (
			self.status not in [CurrentLevelState.FINISHED, CurrentLevelState.SKIPPED, CurrentLevelState.TIMEOUT] or 
			self.time_finish is None
		):
			raise LogValidationError(f'Continue click on unfinished level, status={self.status}, time_finish={self.time_finish}')
	

	def skip(self, time_skip: TIMESTAMP_MS):
		if self.status != CurrentLevelState.STARTED:
			raise LogValidationError(f'Cannot skip {self.slide_type} with status {self.status}')

		self.status = CurrentLevelState.SKIPPED
		self.time_finish = time_skip
