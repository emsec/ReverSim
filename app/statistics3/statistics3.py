from datetime import datetime
from enum import StrEnum
import os
from typing import Iterable

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from app.config import PHASES_WITH_LEVELS
from app.gameConfig import ALL_LEVEL_TYPES, LEVEL_FILETYPES_WITH_TASK, GameConfig
from app.model.LevelLoader.JsonLevelList import JsonLevelList
from app.model.LevelLoader.LevelLoader import LevelLoader
from app.model.LogEvents import AltTaskEvent, ChronoEvent, ClickEvent, ConfirmClickEvent, DrawEvent, GameOverEvent, GroupAssignmentEvent, IntroNavigationEvent, LanguageSelectionEvent, LogCreatedEvent, LogEvent, PopUpEvent, QualiEvent, ReconnectEvent, RedirectEvent, SelectDrawToolEvent, SimulateEvent, SkillAssessmentEvent, StartSessionEvent, SwitchClickEvent
from app.statistics.statisticUtils import LogSyntaxError
from app.utilsGame import LevelType, PhaseType

# Flask uses an instance folder to store and load assets
INSTANCE_FOLDER = os.path.abspath(os.environ.get('REVERSIM_INSTANCE', './instance'))

# paths are relative to instance folder
CONFIG_NAME = os.environ.get('REVERSIM_CONFIG', 'conf/gameConfig.json')
DATABASE_PATH = os.environ.get('REVERSIM_DATABASE', 'statistics/reversim.db')

type TIMESTAMP_MS = datetime

class CurrentState(StrEnum):
	LOADED = 'Loaded'
	STARTED = 'In Progress'
	FINISHED = 'Finished'


class StatsSlide:
	time_load: TIMESTAMP_MS
	time_start: TIMESTAMP_MS|None
	time_finish: TIMESTAMP_MS|None

	slideType: LevelType
	status: CurrentState = CurrentState.LOADED

	def __init__(self, type_slide: LevelType, time_load: TIMESTAMP_MS) -> None:
		self.slideType = type_slide
		self.time_load = time_load


	def start(self, time_start: TIMESTAMP_MS):
		if self.status != CurrentState.LOADED:
			raise LogSyntaxError(f'Cannot start {self.slideType} with status {self.status}')

		self.status = CurrentState.STARTED
		self.time_start = time_start


	def finish(self, time_finish: TIMESTAMP_MS):
		if self.status != CurrentState.STARTED:
			raise LogSyntaxError(f'Cannot finish {self.slideType} with status {self.status}')
		
		self.status = CurrentState.FINISHED
		self.time_finish = time_finish


class StatsCircuit(StatsSlide):
	switchClicks: int = 0
	minSwitchClicks: int|None = None
	confirmClicks: int = 0

	def click_switch(self):
		self.switchClicks += 1


class StatsAltTask(StatsSlide):
	pass


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
			raise LogSyntaxError(f'Cannot start {self.phaseType} with status {self.status}')

		self.status = CurrentState.STARTED
		self.time_start = time_start

	def finish(self, time_finish: TIMESTAMP_MS):
		if self.status != CurrentState.STARTED:
			raise LogSyntaxError(f'Cannot finish {self.phaseType} with status {self.status}')
		
		self.status = CurrentState.FINISHED
		self.time_finish = time_finish


class StatsPhaseLevels(StatsPhase):
	
	levels: list[StatsSlide] = []
	_active_level: StatsSlide|None = None

	@property
	def activeLevel(self):
		assert self._active_level in self.levels
		return self._active_level
	

	def __init__(self, type_phase: PhaseType, time_load: TIMESTAMP_MS) -> None:
		super().__init__(type_phase, time_load)
		assert type_phase in PHASES_WITH_LEVELS

	
	def load_level(self, type_level: str, time_load: TIMESTAMP_MS):
		try:
			levelType = LevelType(type_level)
		except Exception:
			raise LogSyntaxError('Unexpected phase type in database')
		
		if levelType in LEVEL_FILETYPES_WITH_TASK:
			level = StatsCircuit(levelType, time_load)
		else:
			level = StatsSlide(levelType, time_load)

		self.levels.append(level)
		self._activeLevel = level


class StatsParticipant:
	pseudonym: str

	phases: list[StatsPhase] = []
	_activePhase: StatsPhase|None = None

	@property
	def activePhase(self):
		assert self._activePhase in self.phases
		return self._activePhase
	

	def load_phase(self, type_phase: str, time_loaded: TIMESTAMP_MS):
		try:
			phaseType = PhaseType(type_phase)
		except Exception:
			raise LogSyntaxError('Unexpected phase type in database')
		
		if phaseType in PHASES_WITH_LEVELS:
			phase = StatsPhaseLevels(phaseType, time_loaded)
		else:
			phase = StatsPhase(phaseType, time_loaded)

		self.phases.append(phase)
		self._activePhase = phase


class StatisticsGenerator:
	def __init__(self, 
		instance_path: str, 
		gameConfig: GameConfig,
		levelLoader: type[LevelLoader],
		database: Engine
	) -> None:
	
		self.instance_path = instance_path
		self.gameConfig = gameConfig
		self.levelLoader = levelLoader
		self.engine = database


	def read_group(self, group: str):
		pass

	
	def read_participant(self, pseudonym: str):
		with Session(self.engine) as session:
			
			participant = StatsParticipant()
			events: Iterable[LogEvent] = session.scalars(
				statement=select(LogEvent).where(LogEvent.pseudonym == pseudonym)
			)

			for event in events:
				try:
					match event.eventType:
						case LogCreatedEvent.__name__:
							self.event_log_created(session, participant, event)
						case LanguageSelectionEvent.__name__:
							pass
						case GroupAssignmentEvent.__name__:
							pass
						case RedirectEvent.__name__:
							pass
						case ReconnectEvent.__name__:
							pass
						case GameOverEvent.__name__:
							pass
						case ChronoEvent.__name__:
							self.event_chrono(session, participant, event)
						case StartSessionEvent.__name__:
							pass
						case SkillAssessmentEvent.__name__:
							pass
						case QualiEvent.__name__:
							pass
						case ClickEvent.__name__:
							pass
						case SwitchClickEvent.__name__:
							self.event_switch_click(session, participant, event)
						case ConfirmClickEvent.__name__:
							self.event_confirm_click(session, participant, event)
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
							raise LogSyntaxError('Unexpected Log Type')
				
				# Add the originating event of this error the the exception
				except LogSyntaxError as e:
					e.originLine = event.id
					raise e


	def event_log_created(self, session: Session, participant: StatsParticipant, event: LogEvent):
		assert isinstance(event, LogCreatedEvent)

		participant.pseudonym = event.plain_pseudonym

		if event.plain_pseudonym != event.pseudonym:
			raise LogSyntaxError(f'Pseudonym mismatch in LogCreatedEvent: "{event.plain_pseudonym} != {event.pseudonym}"')


	def event_chrono(self, session: Session, participant: StatsParticipant, event: LogEvent):
		assert isinstance(event, ChronoEvent)
		
		if event.timeClient is None:
			raise LogSyntaxError('The chrono event did not contain the client time')

		if 'phase' == event.timerType:
			if 'load' == event.operation:
				participant.load_phase(event.timerName, event.timeClient)
			elif 'start' == event.operation:
				participant.activePhase.start(event.timeClient)
			else:
				raise LogSyntaxError(f'Unknown operation "{event.operation}"')
				

		elif event.timerType in ALL_LEVEL_TYPES:
			if 'load' == event.operation:
				
			elif 'start' == event.operation:

			else:
				raise LogSyntaxError(f'Unknown operation "{event.operation}"')
			


	def event_switch_click(self, session: Session, participant: StatsParticipant, event: LogEvent):
		assert isinstance(event, SwitchClickEvent)


	def event_confirm_click(self, session: Session, participant: StatsParticipant, event: LogEvent):
		assert isinstance(event, ConfirmClickEvent)


def main():

	gameConfig = GameConfig(
		configName=CONFIG_NAME,
		instanceFolder=INSTANCE_FOLDER
	)

	JsonLevelList.singleton = JsonLevelList.fromFile(instanceFolder=INSTANCE_FOLDER)

	database_path = os.path.join(INSTANCE_FOLDER, DATABASE_PATH)
	engine = (create_engine("sqlite://" + database_path, echo=True)
		.execution_options(sqlite_readonly = True))

	statsGenerator = StatisticsGenerator(INSTANCE_FOLDER, gameConfig, JsonLevelList, engine)


if __name__ == '__main__':
	main()
