class GameStateValidator:
	"""
	Ensure that the player logfile/statistic is plausible when compared to the last saved
	game state in the [reversim.db](instance/statistics/reversim.db) player database.
	"""

	# TODO


	def validate():
		
		# The phase from the game state
		assert statsParticipant.phaseIdx is not None
		gamestate_phase = player.phases[statsParticipant.phaseIdx]

		# Check that the phase type matches what was shown during the game
		if gamestate_phase.name != phaseType:
			raise LogValidationError(f'{phaseType} does not match the gamestate {gamestate_phase.name}')

		# Assert that a phase with levels really has levels
		assert phaseType in PHASES_WITH_LEVELS and len(gamestate_phase.levels) > 0, (
			f'Phase {phaseType} is expected to have no levels, but gameState has {len(gamestate_phase.levels)}'
		)
		
		# Assert that a phase without levels really has no levels
		assert phaseType not in PHASES_WITH_LEVELS and len(gamestate_phase.levels) < 1, (
			f'Phase {phaseType} is expected to have levels, but gameState has 0'
		)
