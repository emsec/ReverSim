from datetime import timedelta
from app.gameConfig import PHASES_WITH_LEVELS
from app.statistics3.StatsPhase import StatsPhase
from app.statistics3.StatsPhaseLevels import StatsPhaseLevels
from app.statistics3.statisticsUtils import TIMESTAMP_MS, LogValidationError
from app.utilsGame import PhaseType


class StatsParticipant:

	@property
	def activePhase(self) -> StatsPhase:
		assert self.phaseIdx >= 0 and self.phaseIdx < len(self.phases)
		return self.phases[self.phaseIdx]
	

	def __init__(self, pseudonym: str, is_debug: bool) -> None:
		self.pseudonym = pseudonym
		self.is_debug = is_debug

		self.is_debug: bool
		self.groups: list[str] = []

		self.phases: list[StatsPhase] = []
		self.phaseIdx: int = -1

		self.quali_fails: int = 0

		self.game_started = False
		self.reloads: list[str] = []

		self.time_limit: timedelta|None = None


	def load_phase(self, type_phase: str, time_loaded: TIMESTAMP_MS):
		try:
			phaseType = PhaseType(type_phase)
		except Exception:
			raise LogValidationError('Unexpected phase type in database')

		if phaseType in PHASES_WITH_LEVELS:
			phase = StatsPhaseLevels(phaseType, time_loaded)
		else:
			phase = StatsPhase(phaseType, time_loaded)

		self.phases.append(phase)
		self.phaseIdx = len(self.phases) - 1

