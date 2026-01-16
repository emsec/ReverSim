from dataclasses import dataclass, field
from datetime import timedelta
from app.gameConfig import PHASES_WITH_LEVELS
from app.statistics3.StatsPhase import StatsPhase
from app.statistics3.StatsPhaseLevels import StatsPhaseLevels
from app.statistics3.statisticsUtils import TIMESTAMP_MS, LogValidationError
from app.utilsGame import PhaseType

@dataclass
class StatsParticipant:

	pseudonym: str
	is_debug: bool

	groups: list[str] = field(default_factory=list[str])

	phases: list[StatsPhase] = field(default_factory=list[StatsPhase])
	phaseIdx: int = -1

	quali_fails: int = 0

	game_started: bool = False
	reloads: list[str] = field(default_factory=list[str])

	time_limit: timedelta|None = None

	@property
	def activePhase(self) -> StatsPhase:
		assert self.phaseIdx >= 0 and self.phaseIdx < len(self.phases)
		return self.phases[self.phaseIdx]


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

