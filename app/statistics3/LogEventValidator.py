from datetime import timedelta
import logging

from sqlalchemy.orm import Session

from app.gameConfig import ALL_LEVEL_TYPES
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
	LogEventLevel,
	LogEventPhase,
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
from app.statistics3.StatsCircuit import StatsCircuit
from app.statistics3.StatsParticipant import StatsParticipant
from app.statistics3.StatsPhaseLevels import StatsPhaseLevels
from app.utilsGame import ClickableObjects, LevelType, PhaseType, getShortPseudo


class LogEventValidator():

	def handle_event(self, event: LogEvent, session: Session, statsParticipant: StatsParticipant, player: Participant):
		match event.eventType:
			case LogCreatedEvent.__tablename__:
				assert isinstance(event, LogCreatedEvent)
				self.event_log_created(statsParticipant, event)
			case LanguageSelectionEvent.__tablename__:
				pass
			case GroupAssignmentEvent.__tablename__:
				assert isinstance(event, GroupAssignmentEvent)
				self.event_group_assignment(statsParticipant, event)
			case RedirectEvent.__tablename__:
				pass
			case ReconnectEvent.__tablename__:
				pass
			case GameOverEvent.__tablename__:
				pass
			case ChronoEvent.__tablename__:
				assert isinstance(event, ChronoEvent)
				self.event_chrono(statsParticipant, player, event)
			case StartSessionEvent.__tablename__:
				assert isinstance(event, StartSessionEvent)
				self.event_start_session(statsParticipant, event)
			case SkillAssessmentEvent.__tablename__:
				pass
			case QualiEvent.__tablename__:
				assert isinstance(event, QualiEvent)
				self.event_quali(statsParticipant, event)
			case ClickEvent.__tablename__:
				assert isinstance(event, ClickEvent)
				self.event_click(statsParticipant, event)
			case SwitchClickEvent.__tablename__:
				assert isinstance(event, SwitchClickEvent)
				self.event_switch_click(statsParticipant, event)
			case ConfirmClickEvent.__tablename__:
				assert isinstance(event, ConfirmClickEvent)
				self.event_confirm_click(statsParticipant, event)
			case SimulateEvent.__tablename__:
				pass
			case IntroNavigationEvent.__tablename__:
				pass
			case SelectDrawToolEvent.__tablename__:
				pass
			case DrawEvent.__tablename__:
				pass
			case PopUpEvent.__tablename__:
				pass
			case AltTaskEvent.__tablename__:
				pass
			case _:
				raise LogValidationError('Unexpected Log Type')

		# Most events are associated with a Phase context and Level context where appropriate.
		# 
		if isinstance(event, LogEventPhase):
			assert event.phase is not None
			assert event.phase.activePhase in PhaseType

			# No checks since game was not started yet
			if event.phase.activePhase in [PhaseType.NotStarted, PhaseType.Preload]:
				return

			eventPhase = event.phase.activePhase
			statsPhase = statsParticipant.activePhase.phaseType
			if eventPhase != statsPhase:
				raise LogValidationError(f'Log context says this is {eventPhase} but validator thinks this must be {statsPhase}')
			
			SPECIAL_CASES = [
				ChronoEvent.__tablename__,
				IntroNavigationEvent.__tablename__,
				ClickEvent.__tablename__,
				DrawEvent.__tablename__,
				SwitchClickEvent.__tablename__
			]

			if isinstance(event, LogEventLevel):
				if (
					event.eventType not in SPECIAL_CASES
					and not isinstance(statsParticipant.activePhase, StatsPhaseLevels)
				):
					raise LogValidationError('Should have been StatsPhaseLevels')

				if event.eventType not in SPECIAL_CASES:
					assert isinstance(statsParticipant.activePhase, StatsPhaseLevels)
					eventLevel = event.level_name
					statsLevel = statsParticipant.activePhase.activeLevel.log_name

					if eventLevel != statsLevel:
						raise LogValidationError(f'Log context says this is {eventLevel} but validator thinks this must be {statsLevel}')


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


	def event_chrono(self,
		participant: StatsParticipant,
		player: Participant,
		event: ChronoEvent
	):
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
				raise LogValidationError(
					f'Slide type {event.timerType} should not exist in phase {participant.activePhase}',
					event
				)

			# Load a Slide
			if 'load' == event.operation:
				self.load_slide(event, participant)
			
			# Start a slide
			elif 'start' == event.operation:
				self.start_slide(event, participant)

			elif 'stop' == event.operation:
				self.stop_slide(event, participant)

			else:
				raise LogValidationError(f'Unknown operation "{event.operation}"', event)
		
		# Phase Time Limit Operations
		elif 'countdown' == event.timerType:
			if 'start' == event.operation:
				self.start_phase_countdown(participant, event)
			elif 'stop' == event.operation:
				self.stop_phase_countdown(participant, event)
			else:
				raise LogValidationError(f'Unknown timer operation {event.operation}')
		else:
			raise LogValidationError(f'Unknown timer type "{event.timerType}"')


	def event_start_session(self,
		statsParticipant: StatsParticipant,
		event: StartSessionEvent
	):
		assert event.timeClient is not None
		assert event.phase is not None

		# No need to set the page reload flag, if this is the first launch
		if not statsParticipant.game_started:
			statsParticipant.game_started = True
			statsParticipant.start_time = event.timeClient
			return

		# Otherwise at this point this must be a page reload
		statsParticipant.activePhase.reloaded = True
		levelName = ''

		if isinstance(statsParticipant.activePhase, StatsPhaseLevels):
			statsParticipant.activePhase.activeLevel.reloaded = True
			levelName = '@' + statsParticipant.activePhase.activeLevel.log_name

		ui = getShortPseudo(statsParticipant.pseudonym)
		reload_location = statsParticipant.activePhase.phaseType + levelName
		logging.warning(f'Participant {ui} reloaded the page at "{reload_location}"')
		statsParticipant.reloads.append(reload_location)


	def event_quali(self,
		statsParticipant: StatsParticipant,
		event: QualiEvent
	):
		assert event.timeClient is not None
		assert event.phase is not None
		assert event.level is not None

		activePhase = statsParticipant.activePhase
		if activePhase.phaseType is not PhaseType.Quali:
			raise LogValidationError(f'Quali event in phase {activePhase.phaseType}')

		# Increment Quali Fails
		if not event.qualified:
			statsParticipant.quali_fails += 1


	def event_click(self,
		statsParticipant: StatsParticipant,
		event: ClickEvent
	):
		assert event.timeClient is not None
		assert event.phase is not None
		assert event.object in ClickableObjects
		assert event.object not in [ClickableObjects.SWITCH, ClickableObjects.CONFIRM]

		match event.object:
			case ClickableObjects.CONTINUE:
				self.click_continue(statsParticipant, event)
			case ClickableObjects.SKIP:
				self.click_skip(statsParticipant, event)
			case _:
				pass


	def event_switch_click(self,
		statsParticipant: StatsParticipant, 
		event: SwitchClickEvent
	):
		assert event.timeClient is not None
		assert event.phase is not None
		assert event.object == ClickableObjects.SWITCH

		# Ensure the levelState was set
		level_state = event.levelState
		if level_state is None:
			raise LogValidationError('A switch click event must always have a level state')
		
		# IntroduceElements and IntroduceDrawingTools can have a switch click without an active level
		if statsParticipant.activePhase.phaseType in [PhaseType.DrawTools, PhaseType.ElementIntro]:
			return # Do nothing as we dont track switch clicks in the tutorial

		# Otherwise make sure we have a valid level
		elif not isinstance(statsParticipant.activePhase, StatsPhaseLevels):
			raise LogValidationError(
				f'Switch click should not exist in phase {statsParticipant.activePhase}',
				event
			)

		# Switch clicks must only appear in a circuit or in a tutorial
		level = statsParticipant.activePhase.activeLevel
		if not isinstance(level, StatsCircuit) and not level.slide_type == LevelType.TUTORIAL:
			raise LogValidationError(
				f'Switch Click in {level.log_name} which is not a Circuit or Tutorial', event
			)

		# Increment the switch clicks (switch clicks in tutorials are not tracked)
		if isinstance(level, StatsCircuit):
			level.click_switch()


	def event_confirm_click(self,
		statsParticipant: StatsParticipant,
		event: ConfirmClickEvent
	):
		assert event.timeClient is not None
		assert event.phase is not None
		assert event.level is not None
		assert event.object == ClickableObjects.CONFIRM

		# All levels with a task must send the state information
		level_state = event.levelState
		if level_state is None:
			raise LogValidationError('A confirm click event must always have a level state')

		# Otherwise make sure we have a valid level
		if not isinstance(statsParticipant.activePhase, StatsPhaseLevels):
			raise LogValidationError(
				f'Confirm click should not exist in phase {statsParticipant.activePhase}',
				event
			)

		level = statsParticipant.activePhase.activeLevel
		if not isinstance(level, StatsCircuit):
			raise LogValidationError(
				f'Confirm Click in {level.log_name} which is not a Circuit', event
			)
		
		# Increment the confirm clicks
		level.click_confirm(event.timeClient, level_state.solved)


	def load_phase(self,
		event: ChronoEvent,
		statsParticipant: StatsParticipant,
		player: Participant
	):
		assert event.timeClient is not None

		phaseType = event.timerName
		statsParticipant.load_phase(phaseType, event.timeClient)


	def start_phase(self, event: ChronoEvent, statsParticipant: StatsParticipant):
		assert event.timeClient is not None
		assert event.phase is not None

		# Preload events follow directly after event_start_session
		if event.phase.activePhase == PhaseType.Preload:
			if not statsParticipant.game_started or statsParticipant.start_time is None:
				raise LogValidationError('Preload Scene must follow directly after an event_start_phase')
			
			# The Preload event contains the time limit
			if event.limit is not None:
				statsParticipant.time_limit = timedelta(seconds=event.limit)
		
		# If this is not a preload phase, start the phase as usual
		else:
			if event.timerName != statsParticipant.activePhase.phaseType:
				if event.timerName == PhaseType.FinalScene:
					raise LogValidationError(f'Currently active is {statsParticipant.activePhase.phaseType} but log asks for {event.timerName}')

			statsParticipant.activePhase.start(time_start=event.timeClient, time_limit=event.limit)


	def load_slide(self, event: ChronoEvent, statsParticipant: StatsParticipant):
		assert event.timeClient is not None
		assert event.phase is not None
		assert event.level is not None

		activePhase = statsParticipant.activePhase
		if not isinstance(activePhase, StatsPhaseLevels):
			raise LogValidationError('Load event called but Phase has no slides')

		if event.level.levelType != event.timerType:
			raise LogValidationError(f'Implausible timer name: {event.level.levelType} is not {event.timerType}')

		assert event.level_name is not None
		activePhase.load_level(
			type_level=event.timerType,
			log_name=Level.uniformName(event.level_name),
			time_load=event.timeClient
		)


	def start_slide(self, event: ChronoEvent, statsParticipant: StatsParticipant):
		assert event.timeClient is not None
		assert event.phase is not None
		assert event.level is not None

		activePhase = statsParticipant.activePhase
		if not isinstance(activePhase, StatsPhaseLevels):
			raise LogValidationError('Start event called but Phase has no slides')

		activePhase.activeLevel.start(time_start=event.timeClient, time_limit=event.limit)


	def stop_slide(self, event: ChronoEvent, statsParticipant: StatsParticipant):
		assert event.timeClient is not None
		assert event.phase is not None
		assert event.level is not None
		assert isinstance(statsParticipant.activePhase, StatsPhaseLevels)

		statsParticipant.activePhase.activeLevel.stop(event.timeClient)


	def start_phase_countdown(self, statsParticipant: StatsParticipant, event: ChronoEvent):
		assert event.timeClient is not None
		
		statsParticipant.activePhase.start_phase_time_limit(event.timeClient)


	def stop_phase_countdown(self, statsParticipant: StatsParticipant, event: ChronoEvent):
		assert event.timeClient is not None
		
		if not isinstance(statsParticipant.activePhase, StatsPhaseLevels):
			raise LogValidationError('Countdown event can only occur in phase with levels')
		
		statsParticipant.activePhase.stop_phase_time_limit(event.timeClient)


	def click_continue(self,
		statsParticipant: StatsParticipant,
		event: ClickEvent
	):
		assert event.timeClient is not None
		assert event.object == ClickableObjects.CONTINUE

		if statsParticipant.activePhase.phaseType == PhaseType.AltTask:
			logging.info('End of Phase AltTask')
			return

		# If it is a level continue
		if isinstance(statsParticipant.activePhase, StatsPhaseLevels):
			activeLevel = statsParticipant.activePhase.activeLevel

			# The user should only be able to continue a solved level
			if event.levelState is not None and not event.levelState.solved:
				raise LogValidationError('Continue clicked on an unfinished level')

			activeLevel.click_continue(time_finish=event.timeClient)

		# Else this must be the end of a Phase
		else:
			logging.info(f'End of Phase {statsParticipant.activePhase.phaseType}')


	def click_skip(self,
		statsParticipant: StatsParticipant,
		event: ClickEvent
	):
		assert event.timeClient is not None
		assert event.object == ClickableObjects.SKIP

		# Slides with task can only exist in certain phases
		if not isinstance(statsParticipant.activePhase, StatsPhaseLevels):
			raise LogValidationError('Skip only valid in a Phase with levels')
		
		# Ensure slide contains a task
		activeLevel = statsParticipant.activePhase.activeLevel
		if not isinstance(activeLevel, StatsCircuit):
			raise LogValidationError('Skip click on a slide without a task')
		
		# Handle skip event
		activeLevel.skip(time_skip=event.timeClient)
