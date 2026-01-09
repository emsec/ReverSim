from app.statistics3.StatsSlide import StatsSlide
from app.statistics3.statisticsUtils import TIMESTAMP_MS, CurrentState, LogValidationError


class StatsCircuit(StatsSlide):
	switchClicks: int = 0
	minSwitchClicks: int|None = None
	confirmClicks: int = 0

	def click_switch(self):
		if self.status != CurrentState.STARTED:
			raise LogValidationError(f'Cannot click switch in {self.slide_type} with status {self.status}')
		
		self.switchClicks += 1

	
	def skip(self, time_skip: TIMESTAMP_MS):
		if self.status != CurrentState.STARTED:
			raise LogValidationError(f'Cannot skip {self.slide_type} with status {self.status}')
		
		self.time_finish = time_skip

