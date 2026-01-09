from sqlalchemy.orm import Session

from app.gameConfig import ALL_LEVEL_TYPES, PHASES_WITH_LEVELS
from app.model.Level import Level
from app.model.LogEvents import (
	AltTaskEvent,
	ChronoEvent,
	ClickEvent,
	ConfirmClickEvent,
	DrawEvent,
	GameOverEvent,
	GroupAssignmentEvent,
	IntroNavigationEvent,
	LanguageSelectionEvent,
	LogCreatedEvent,
	LogEvent,
	PopUpEvent,
	QualiEvent,
	ReconnectEvent,
	RedirectEvent,
	SelectDrawToolEvent,
	SimulateEvent,
	SkillAssessmentEvent,
	StartSessionEvent,
	SwitchClickEvent,
)

from app.model.Participant import Participant
from app.statistics3.statisticsUtils import LogValidationError
from app.statistics3.StatsParticipant import StatsParticipant
from app.statistics3.StatsPhaseLevels import StatsPhaseLevels


class LogEventValidator():

	def handle_event(self, event: LogEvent, session: Session, statsParticipant: StatsParticipant, player: Participant):
		match event.eventType:
			case LogCreatedEvent.__name__:
				assert isinstance(event, LogCreatedEvent)
				self.event_log_created(statsParticipant, event)
			case LanguageSelectionEvent.__name__:
				pass
			case GroupAssignmentEvent.__name__:
				assert isinstance(event, GroupAssignmentEvent)
				self.event_group_assignment(statsParticipant, event)
			case RedirectEvent.__name__:
				pass
			case ReconnectEvent.__name__:
				pass
			case GameOverEvent.__name__:
				pass
			case ChronoEvent.__name__:
				assert isinstance(event, ChronoEvent)
				self.event_chrono(session, statsParticipant, player, event)
			case StartSessionEvent.__name__:
				pass
			case SkillAssessmentEvent.__name__:
				pass
			case QualiEvent.__name__:
				pass
			case ClickEvent.__name__:
				pass
			case SwitchClickEvent.__name__:
				assert isinstance(event, SwitchClickEvent)
				self.event_switch_click(session, statsParticipant, event)
			case ConfirmClickEvent.__name__:
				assert isinstance(event, ConfirmClickEvent)
				self.event_confirm_click(session, statsParticipant, event)
			case SimulateEvent.__name__:
				pass
			case IntroNavigationEvent.__name__:
				pass
			case SelectDrawToolEvent.__name__:
				pass
			case DrawEvent.__name__:
				pass
			case PopUpEvent.__name__:
				pass
			case AltTaskEvent.__name__:
				pass
			case _:
				raise LogValidationError('Unexpected Log Type')


	def event_log_created(self,
		participant: StatsParticipant,
		event: LogCreatedEvent
	):
		participant.pseudonym = event.plain_pseudonym

		if event.plain_pseudonym != event.pseudonym:
			raise LogValidationError(f'Pseudonym mismatch in LogCreatedEvent: "{event.plain_pseudonym} != {event.pseudonym}"')


	def event_group_assignment(self,
		statsParticipant: StatsParticipant,
		event: GroupAssignmentEvent
	):

		if event.group in statsParticipant.groups:
			raise LogValidationError(f'Group {event.group} was assigned twice', event)

		statsParticipant.groups.append(event.group)


	def event_chrono(self, session: Session, participant: StatsParticipant, player: Participant, event: ChronoEvent):
		if event.timeClient is None:
			raise LogValidationError('The chrono event did not contain the client time')

		# Phase Operations
		if 'phase' == event.timerType:
			# Phase Load
			if 'load' == event.operation:
				self.load_phase(event, participant, player)
							
			# Phase Start
			elif 'start' == event.operation:
				self.start_phase(event, participant)
				
			else:
				raise LogValidationError(f'Unknown operation "{event.operation}"')
				
		# Level Operations
		elif event.timerType in ALL_LEVEL_TYPES:
			# Check that the Level/Info Slide was created in a Phase which supports them
			if not isinstance(participant.activePhase, StatsPhaseLevels):
				raise LogValidationError(f'Slide type {event.timerType} should not exist in phase {participant.activePhase}', event)

			# Load a Slide
			if 'load' == event.operation:
				self.load_slide(event, participant)
			
			# Start a slide
			elif 'start' == event.operation:
				self.start_slide(event, participant)

			else:
				raise LogValidationError(f'Unknown operation "{event.operation}"')


	def event_switch_click(self, session: Session, statsParticipant: StatsParticipant, event: SwitchClickEvent):
		statsParticipant.activePhase


	def event_confirm_click(self, session: Session, statsParticipant: StatsParticipant, event: ConfirmClickEvent):
		statsParticipant.activePhase


	def load_phase(self, event: ChronoEvent, statsParticipant: StatsParticipant, player: Participant):
		assert event.timeClient is not None

		phaseType = event.timerName
		statsParticipant.load_phase(phaseType, event.timeClient)

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


	def start_phase(self, event: ChronoEvent, statsParticipant: StatsParticipant):
		assert event.timeClient is not None

		statsParticipant.activePhase.start(event.timeClient)


	def load_slide(self, event: ChronoEvent, statsParticipant: StatsParticipant):
		assert event.timeClient is not None

		activePhase = statsParticipant.activePhase
		if not isinstance(activePhase, StatsPhaseLevels):
			raise LogValidationError('')

		activePhase.load_level(
			type_level=event.timerType,
			log_name=Level.uniformName(event.timerName),
			time_load=event.timeClient
		)


	def start_slide(self, event: ChronoEvent, statsParticipant: StatsParticipant):
		assert event.timeClient is not None

