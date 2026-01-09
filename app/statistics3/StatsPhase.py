
from app.statistics3.statisticsUtils import TIMESTAMP_MS, CurrentState, LogValidationError
from app.utilsGame import PhaseType


class StatsPhase:
	time_load: TIMESTAMP_MS
	time_start: TIMESTAMP_MS|None
	time_finish: TIMESTAMP_MS|None

	phaseType: PhaseType
	status: CurrentState = CurrentState.LOADED

	def __init__(self, type_phase: PhaseType, time_load: TIMESTAMP_MS) -> None:
		self.phaseType = type_phase
		self.time_load = time_load


	def start(self, time_start: TIMESTAMP_MS):
		if self.status != CurrentState.LOADED:
			raise LogValidationError(f'Cannot start {self.phaseType} with status {self.status}')

		self.status = CurrentState.STARTED
		self.time_start = time_start


	def finish(self, time_finish: TIMESTAMP_MS):
		if self.status != CurrentState.STARTED:
			raise LogValidationError(f'Cannot finish {self.phaseType} with status {self.status}')
		
		self.status = CurrentState.FINISHED
		self.time_finish = time_finish

