from app.gameConfig import LEVEL_FILETYPES_WITH_TASK, PHASES_WITH_LEVELS
from app.statistics3.StatsCircuit import StatsCircuit
from app.statistics3.StatsPhase import StatsPhase
from app.statistics3.StatsSlide import StatsSlide
from app.statistics3.statisticsUtils import TIMESTAMP_MS, LogValidationError
from app.utilsGame import LevelType, PhaseType


class StatsPhaseLevels(StatsPhase):

	@property
	def activeLevel(self) -> StatsSlide:
		assert self.levelIdx >= 0 and self.levelIdx < len(self.levels)
		return self.levels[self.levelIdx]
	

	def __init__(self, type_phase: PhaseType, time_load: TIMESTAMP_MS) -> None:
		super().__init__(type_phase, time_load)
		assert type_phase in PHASES_WITH_LEVELS

		self.levels: list[StatsSlide] = []
		self.levelIdx: int = -1

	
	def load_level(self, type_level: str, log_name: str, time_load: TIMESTAMP_MS):
		try:
			levelType = LevelType(type_level)
		except Exception:
			raise LogValidationError('Unexpected phase type in database')

		if levelType in LEVEL_FILETYPES_WITH_TASK:
			level = StatsCircuit(levelType, log_name=log_name, time_load=time_load)
		else:
			level = StatsSlide(levelType, log_name=log_name, time_load=time_load)

		self.levels.append(level)
		self.levelIdx = len(self.levels) - 1
