from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.gameConfig import PHASES_WITH_LEVELS
from app.model.Level import Level
from app.model.Participant import Participant
from app.model.Phase import Phase
from app.statistics3.StatsCircuit import StatsCircuit
from app.statistics3.StatsParticipant import StatsParticipant
from app.statistics3.StatsPhase import StatsPhase
from app.statistics3.StatsPhaseLevels import StatsPhaseLevels
from app.statistics3.statisticsUtils import TIME_TOLERANCE, LogValidationError

class GameStateValidator:
	"""
	Ensure that the player logfile/statistic is plausible when compared to the last saved
	game state in the [reversim.db](instance/statistics/reversim.db) player database.
	"""

	def validate(self, participant: StatsParticipant, session: Session):
		
		player = session.get_one(Participant, participant.pseudonym)
		
		for i, stats_phase in enumerate(participant.phases):
			# The phase from the game state
			assert participant.phaseIdx is not None
			gamestate_phase = player.phases[i]

			self.validate_phase(stats_phase, gamestate_phase)


	def validate_phase(self, stats_phase: StatsPhase, gamestate_phase: Phase):
		# Check that the phase type matches what was shown during the game
		if gamestate_phase.name != stats_phase.phaseType:
			raise LogValidationError(f'{stats_phase.phaseType} does not match the gamestate {gamestate_phase.name}')

		# Assert that a phase with levels really has levels
		if stats_phase.phaseType in PHASES_WITH_LEVELS:
			assert len(gamestate_phase.levels) > 0, (
				f'Phase {stats_phase.phaseType} is expected to have no levels, but gameState has {len(gamestate_phase.levels)}'
			)
		
		# Assert that a phase without levels really has no levels
		else:
			assert len(gamestate_phase.levels) < 1, (
				f'Phase {stats_phase.phaseType} is expected to have levels, but gameState has 0'
			)

		if isinstance(stats_phase, StatsPhaseLevels):
			for i, stats_level in enumerate(stats_phase.levels):
				# We are only interested in slides with circuit
				if not isinstance(stats_level, StatsCircuit):
					continue

				self.validate_level(stats_level, gamestate_phase.levels[i])


	def validate_level(self, stats_level: StatsCircuit, gamestate_level: Level):
		if stats_level.slide_type != gamestate_level.type:
			raise LogValidationError(f'Type {stats_level.slide_type}(stats) != {gamestate_level.type}(db)')

		db_level_name = Level.uniformName(gamestate_level.fileName)
		db_level_start = datetime.fromtimestamp(gamestate_level.getStartTime()/1000, tz=timezone.utc)
		db_level_finish = datetime.fromtimestamp(gamestate_level.timeFinished/1000, tz=timezone.utc)

		if stats_level.log_name != db_level_name:
			raise LogValidationError(f'Name {stats_level.log_name}(stats) != {db_level_name}(db)')

		if stats_level.switchClicks != gamestate_level.switchClicks:
			raise LogValidationError(f'Switch {stats_level.switchClicks}(stats) != {gamestate_level.switchClicks}(db)')

		if stats_level.confirmClicks != gamestate_level.confirmClicks:
			raise LogValidationError(f'Confirm {stats_level.confirmClicks}(stats) != {gamestate_level.confirmClicks}(db)')

		if stats_level.time_start is not None:
			stats_start = stats_level.time_start.replace(tzinfo=timezone.utc)
			if (stats_start - db_level_start).total_seconds() > TIME_TOLERANCE:
				raise LogValidationError(f'Start Time {stats_start}(stats) != {db_level_start}(db)')
		
		if stats_level.time_finish is not None:
			stats_finish = stats_level.time_finish.replace(tzinfo=timezone.utc)
			if (stats_finish - db_level_finish).total_seconds() > TIME_TOLERANCE:
				raise LogValidationError(f'Finish Time {stats_finish}(stats) != {db_level_finish}(db)')
