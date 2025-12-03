from datetime import datetime, timezone
import logging
from typing import Annotated, Any, ClassVar, Optional

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import ALL_LEVEL_TYPES, PSEUDONYM_LENGTH
from app.model.Level import Level
from app.storage.database import (
	LEN_GIT_HASH_S,
	LEN_GROUP,
	LEN_LEVEL,
	LEN_LEVEL_TYPE,
	LEN_PHASE,
	LEN_VERSION,
	db,
)
from app.utilsGame import ClickableObjects, EventType, LevelType, PhaseType

LEN_EVENT_TYPE = 32
primary_key = Annotated[int, mapped_column(primary_key=True, autoincrement=True)]

class PlayerContext(db.Model):
	__tablename__ = "player_context"
	pseudonym: Mapped[str] = mapped_column(String(PSEUDONYM_LENGTH), primary_key=True)
	loggingEnabled: Mapped[bool]


	def __init__(self, pseudonym: str, loggingEnabled: bool):
		assert len(pseudonym) == PSEUDONYM_LENGTH, f"Expected a different pseudonym length, got {len(pseudonym)}"
		self.pseudonym = pseudonym
		self.loggingEnabled = loggingEnabled


	@staticmethod
	def createPlayer(pseudonym: str, loggingEnabled: bool):
		p = PlayerContext(pseudonym, loggingEnabled)
		db.session.add(p)
		db.session.commit()


class PhaseContext(db.Model):
	__tablename__ = "phase_context"

	activePhase: Mapped[str] = mapped_column(String(LEN_PHASE), primary_key=True)

	def __init__(self, phase: str):
		assert phase in PhaseType, f'Unknown Phase "{phase}"!'
		self.activePhase = phase


class LevelContext(db.Model):
	__tablename__ = "level_context"
	levelType: Mapped[LevelType] = mapped_column(Enum(LevelType))
	levelName: Mapped[str] = mapped_column(String(LEN_LEVEL), primary_key=True)

	#__table_args__ = (UniqueConstraint("levelType", "levelName"),)
	
	def __init__(self, levelType: LevelType, levelName: str):
		assert levelType in LevelType, f'Unknown level type "{levelType}"!'
		assert len(levelName) > 0, "An empty string is not a valid level name!"
		self.levelType = levelType
		self.levelName = levelName


class LevelState(db.Model):
	__tablename__ = "level_state"
	id: Mapped[primary_key] = mapped_column(primary_key=True, autoincrement=True)

	levelEvent_id: Mapped[int] = mapped_column(ForeignKey("event.id"))
	levelEvent: Mapped['LogEventLevel'] = relationship(back_populates="levelState")

	solved: Mapped[bool]
	s_switch: Mapped[dict[str, Any] | None] = mapped_column(JSON)
	s_bulb: Mapped[dict[str, Any] | None] = mapped_column(JSON)
	s_danger: Mapped[dict[str, Any] | None] = mapped_column(JSON)
	s_not: Mapped[dict[str, Any] | None] = mapped_column(JSON)
	s_and: Mapped[dict[str, Any] | None] = mapped_column(JSON)
	s_or: Mapped[dict[str, Any] | None] = mapped_column(JSON)

	def __init__(self, 
			solved: bool, 
			s_switch: dict[str, int] | None,
			s_bulb: dict[str, int] | None,
			s_danger: dict[str, int] | None,
			s_not: dict[str, int] | None,
			s_and: dict[str, int] | None,
			s_or: dict[str, int] | None
		) -> None:

		self.solved = solved
		self.s_switch = s_switch
		self.s_bulb = s_bulb
		self.s_danger = s_danger
		self.s_not = s_not
		self.s_and = s_and
		self.s_or = s_or
		
		# If the switches are None, we expect no other gates as we should be inside
		# ElementIntro or IntroduceDrawingTools
		if s_switch is None:
			assert [s_bulb, s_danger, s_not, s_and, s_or].count(None) == 5, "Switches are None, however some logic gates where send"


class LogEvent(db.Model):
	__tablename__ = "event"
	__mapper_args__ = {
		"polymorphic_on": "eventType" # Refers to the attribute/column with that name
	}

	# Attributes that make up the sql entry
	id: Mapped[primary_key] = mapped_column(primary_key=True, autoincrement=True)
	timeClient: Mapped[Optional[datetime]] = mapped_column(DateTime) # Client time
	timeServer: Mapped[datetime] = mapped_column(DateTime) # Server time
	player: Mapped[PlayerContext] = relationship()
	pseudonym: Mapped[str] = mapped_column(ForeignKey(PlayerContext.pseudonym))

	eventType: Mapped[str] = mapped_column(String(LEN_EVENT_TYPE)) # Discriminator

	# Attributes that are not persisted
	event: ClassVar[str]

	def __init__(self, clientTime: int | None, serverTime: int, pseudonym: str) -> None:
		if clientTime is not None: 
			assert clientTime > 0, "Client time is negative or 0!"
		assert serverTime > 0, "Server time is negative or 0!"

		# Set Client Time
		if (clientTime is not None):
			self.timeClient = datetime.fromtimestamp(float(clientTime)/1000, timezone.utc)
		else:
			self.timeClient = None

		# Set Server Time
		self.timeServer = datetime.fromtimestamp(float(serverTime)/1000, timezone.utc)
		self.setPlayerContext(pseudonym)
		LogEvent.event = "ERROR EVENT NOT SET"


	def setPlayerContext(self, pseudonym: str):
		assert len(pseudonym) == PSEUDONYM_LENGTH, f"Expected a different pseudonym length, got {len(pseudonym)}"
		self.player = db.session.get_one(PlayerContext, pseudonym)


	def commit(self) -> bool:
		if not self.player.loggingEnabled:
			return False

		db.session.add(self)
		#db.session.commit()
		return True


class LogEventPhase(LogEvent):
	"""Events that have an active Phase context."""
	__mapper_args__ = {
		"polymorphic_abstract": True
	}

	# NOTE Ideally this attribute wouldn't be added to the parent class but there is no
	# way of telling SQLAlchemy to add it to the inheriting class. Therefore this attribute
	# might become null for events without a phase which forces us to lift the NOT NULL
	# constraint...
	phase_id: Mapped[int | None] = mapped_column(ForeignKey(PhaseContext.activePhase))
	phase: Mapped[PhaseContext | None] = relationship()

	def __init__(self, 
			clientTime: int | None, serverTime: int,
			pseudonym: str, phase: str
		) -> None:

		super().__init__(
			clientTime=clientTime, 
			serverTime=serverTime,
			pseudonym=pseudonym
		)
		self.setPhaseContext(phaseName=phase)


	def setPhaseContext(self, phaseName: str):
		self.phase = db.session.get(PhaseContext, phaseName)

		if self.phase is None:
			logging.info(f'Created phase "{phaseName}".')
			self.phase = PhaseContext(phaseName)
			db.session.add(self.phase)
			db.session.commit()


class LogEventLevel(LogEventPhase):
	"""Events that have an active Slide (Level/Info/...) context."""
	__mapper_args__ = {
		"polymorphic_abstract": True
	}

	level_name: Mapped[str | None] = mapped_column(ForeignKey(LevelContext.levelName))
	#level_type: Mapped[LevelType | None] = mapped_column(ForeignKey(LevelContext.levelType))
	level: Mapped[LevelContext | None] = relationship(foreign_keys=[level_name])

	levelState: Mapped[LevelState | None] = relationship(back_populates="levelEvent")


	def __init__(self, 
			clientTime: int | None, 
			serverTime: int,
			pseudonym: str, 
			phase: str,
			level: tuple[LevelType, str] | None
		) -> None:

		super().__init__(clientTime, serverTime, pseudonym, phase)

		if level is not None:
			assert Level.uniformName(level[1]) == level[1], "The passed level name was not uniform (probably contains .txt suffix)"
			self.setLevelContext(*level)


	def setLevelContext(self, levelType: LevelType, levelName: str):
		self.level = db.session.get(LevelContext, {
			#"levelType": levelType, # TODO If there is an info screen and a level with the same name, things go wrong
			"levelName": levelName
		})

		if self.level is None:
			logging.info(f'Created level "{levelName}" ({levelType}).')
			self.level = LevelContext(levelType=levelType, levelName=levelName)
			db.session.add(self.level)
			db.session.commit()


# --- Global Events ---

class LogCreatedEvent(LogEvent):
	""""""
	__tablename__ = "event_log_created"
	__mapper_args__ = {
		"polymorphic_identity": __tablename__
	}
	id: Mapped[primary_key] = mapped_column(ForeignKey(LogEvent.id))

	version: Mapped[str] = mapped_column(String(LEN_VERSION))
	plain_pseudonym: Mapped[str] = mapped_column(String(PSEUDONYM_LENGTH))
	gitHashS: Mapped[str] = mapped_column(String(LEN_GIT_HASH_S))


	def __init__(self, 
			clientTime: int | None, serverTime: int, 
			pseudonym: str, 
			version: str, gitHashS: str
		) -> None:

		super().__init__(
			clientTime=clientTime,
			serverTime=serverTime,
			pseudonym=pseudonym
		)

		LogEvent.event = EventType.CreatedLog
		self.version = version
		self.plain_pseudonym = pseudonym
		self.gitHashS = gitHashS


class LanguageSelectionEvent(LogEvent):
	""""""
	__tablename__ = "event_language_selection"
	__mapper_args__ = {
		"polymorphic_identity": __tablename__ # Refers to the attribute/column with that name
	}
	id: Mapped[primary_key] = mapped_column(ForeignKey(LogEvent.id))

	language: Mapped[str] = mapped_column(String(5)) # e.g. de-DE, but usually only DE/EN

	def __init__(self, 
			clientTime: int | None,
			serverTime: int, 
			pseudonym: str,
			language: str
		) -> None:

		super().__init__(
			clientTime=clientTime, serverTime=serverTime,
			pseudonym=pseudonym
		)
		self.language = language
	


class GroupAssignmentEvent(LogEvent):
	""""""
	__tablename__ = "event_group_assignment"
	__mapper_args__ = {
		"polymorphic_identity": __tablename__ # Refers to the attribute/column with that name
	}
	id: Mapped[primary_key] = mapped_column(ForeignKey(LogEvent.id))

	group: Mapped[str] = mapped_column(String(LEN_GROUP))
	isDebug: Mapped[bool] = mapped_column()

	def __init__(self, 
			clientTime: int | None, serverTime: int,
			pseudonym: str,
			group: str,
			isDebug: bool
		) -> None:

		super().__init__(
			clientTime=clientTime, serverTime=serverTime, 
			pseudonym=pseudonym
		)
		assert len(group.strip()) > 0, "Empty groups are not allowed"

		LogEvent.event = EventType.GroupAssignment
		self.group = group.strip()
		self.isDebug = isDebug


class RedirectEvent(LogEvent):
	""""""
	__tablename__ = "event_redirect"
	__mapper_args__ = {
		"polymorphic_identity": __tablename__ # Refers to the attribute/column with that name
	}
	id: Mapped[primary_key] = mapped_column(ForeignKey(LogEvent.id))

	destination: Mapped[str] = mapped_column(Text())

	def __init__(self, 
			clientTime: int | None, serverTime: int,
			pseudonym: str,
			destination: str
		) -> None:

		super().__init__(
			clientTime=clientTime, 
			serverTime=serverTime,
			pseudonym=pseudonym
		)
		assert len(destination) < 1855, "The URL is too long" # https://stackoverflow.com/a/417184
		
		LogEvent.event = EventType.Redirect
		self.destination = destination


class TimeSyncEvent(LogEvent):
	""""""
	__tablename__ = "event_timesync"
	__mapper_args__ = {
		"polymorphic_identity": __tablename__ # Refers to the attribute/column with that name
	}
	
	def __init__(self,
			clientTime: int,
			serverTime: int,
			pseudonym: str
		) -> None:

		super().__init__(
			clientTime=clientTime,
			serverTime=serverTime,
			pseudonym=pseudonym
		)
		LogEvent.event = EventType.TimeSync


class ReconnectEvent(LogEvent):
	""""""
	__tablename__ = "event_reconnect"
	__mapper_args__ = {
		"polymorphic_identity": __tablename__ # Refers to the attribute/column with that name
	}
	id: Mapped[primary_key] = mapped_column(ForeignKey(LogEvent.id))

	elapsed: Mapped[float]

	def __init__(self,
			clientTime: int | None,
			serverTime: int,
			pseudonym: str,
			elapsed: float
		) -> None:

		super().__init__(
			clientTime=clientTime,
			serverTime=serverTime,
			pseudonym=pseudonym
		)
		LogEvent.event = EventType.BackOnline
		self.elapsed = elapsed


class GameOverEvent(LogEvent):
	""""""
	__tablename__ = "event_gameover"
	__mapper_args__ = {
		"polymorphic_identity": __tablename__ # Refers to the attribute/column with that name
	}
	id: Mapped[primary_key] = mapped_column(ForeignKey(LogEvent.id))

	def __init__(self,
			clientTime: int | None,
			serverTime: int,
			pseudonym: str
		) -> None:

		super().__init__(
			clientTime=clientTime,
			serverTime=serverTime,
			pseudonym=pseudonym
		)
		LogEvent.event = EventType.GameOver


# --- Phase Events ---

class ChronoEvent(LogEventLevel):
	""""""
	__tablename__ = "event_chronograph"
	__mapper_args__ = {
		"polymorphic_identity": __tablename__ # Refers to the attribute/column with that name
	}
	id: Mapped[primary_key] = mapped_column(ForeignKey(LogEventLevel.id))

	operation: Mapped[str] = mapped_column(String(8))
	timerType: Mapped[str] = mapped_column(String(LEN_LEVEL_TYPE))
	timerName: Mapped[str] = mapped_column(String(max(LEN_LEVEL, LEN_PHASE)))
	limit: Mapped[float | None]

	annex: Mapped[dict[str, Any] | None] = mapped_column(JSON)

	def __init__(self, 
			clientTime: int | None,
			serverTime: int,
			pseudonym: str,
			phase: str,
			level: tuple[LevelType, str] | None,
			operation: str,
			timerType: str,
			context: str,
			limit: Optional[float],
			annex: Optional[dict[str, Any]] = None
	):
		super().__init__(
			clientTime=clientTime,
			serverTime=serverTime,
			pseudonym=pseudonym,
			phase=phase,
			level=level
		)
		self.operation = operation
		self.timerType = timerType
		self.timerName = context
		self.limit = limit
		self.annex = annex

		assert timerType in ['phase', 'countdown'] or level is not None, "Level must be set when not a phase timer"

		PHASE_OPERATIONS = {
			'load': EventType.PhaseRequested,
			'start': EventType.PhaseStarted
		}

		if timerType == 'phase':
			LogEvent.event = PHASE_OPERATIONS.get(operation, operation)

		elif timerType in ALL_LEVEL_TYPES:
			levelOperations: dict[str, str] = {
				'load': EventType.LevelRequested + ' ' + ALL_LEVEL_TYPES[LevelType(timerType)],
				'start': EventType.LevelStarted
			}
			LogEvent.event = levelOperations.get(operation, operation)


class StartSessionEvent(LogEventPhase):
	""""""
	__tablename__ = "event_start_session"
	__mapper_args__ = {
		"polymorphic_identity": __tablename__ # Refers to the attribute/column with that name
	}
	id: Mapped[primary_key] = mapped_column(ForeignKey(LogEventPhase.id))

	packetIndex: Mapped[int]

	def __init__(self,
			clientTime: int | None, serverTime: int,
			pseudonym: str,
			phase: str,
			packetIndex: int
		) -> None:

		super().__init__(
			clientTime=clientTime,
			serverTime=serverTime,
			pseudonym=pseudonym,
			phase=phase
		)
		LogEvent.event = EventType.StartSession
		self.packetIndex = packetIndex


class SkillAssessmentEvent(LogEventPhase):
	""""""
	__tablename__ = "event_skill_assessment"
	__mapper_args__ = {
		"polymorphic_identity": __tablename__ # Refers to the attribute/column with that name
	}
	id: Mapped[primary_key] = mapped_column(ForeignKey(LogEventPhase.id))

	def __init__(self,
			clientTime: int | None,
			serverTime: int,
			pseudonym: str,
			phase: str,
			score: float
		) -> None:

		super().__init__(
			clientTime,
			serverTime,
			pseudonym=pseudonym,
			phase=phase
		)
		LogEvent.event = EventType.SkillAssessment
		self.score = score


# --- Level Events ---

class QualiEvent(LogEventLevel):
	""""""
	__tablename__ = "event_qualified"
	__mapper_args__ = {
		"polymorphic_identity": __tablename__ # Refers to the attribute/column with that name
	}
	id: Mapped[primary_key] = mapped_column(ForeignKey(LogEventLevel.id))

	qualified: Mapped[bool]
	ordinal: Mapped[int] = mapped_column(SmallInteger)

	def __init__(self,
			clientTime: int | None,
			serverTime: int,
			pseudonym: str,
			phase: str,
			level: tuple[LevelType, str],
			qualified: bool,
			ordinal: int
		):

		super().__init__(
			clientTime=clientTime,
			serverTime=serverTime,
			pseudonym=pseudonym,
			phase=phase,
			level=level
		)
		LogEvent.event = f'{EventType.QualiPassed if qualified else EventType.QualiFailed} Quali Level'
		self.qualified = qualified
		self.ordinal = ordinal


class ClickEvent(LogEventLevel):
	""""""
	__tablename__ = "event_click"
	__mapper_args__ = {
		"polymorphic_identity": __tablename__ # Refers to the attribute/column with that name
	}
	id: Mapped[primary_key] = mapped_column(ForeignKey(LogEventLevel.id))

	object: Mapped[ClickableObjects] = mapped_column(Enum(ClickableObjects))

	def __init__(self,
			clientTime: int | None,
			serverTime: int,
			pseudonym: str,
			phase: str,
			level: tuple[LevelType, str] | None,
			object: str
		) -> None:

		super().__init__(
			clientTime=clientTime,
			serverTime=serverTime,
			pseudonym=pseudonym,
			phase=phase,
			level=level
		)
		assert object in ClickableObjects

		LogEvent.event = EventType.Click
		self.object = ClickableObjects(object)


class SwitchClickEvent(ClickEvent):
	""""""
	__tablename__ = "event_click_switch"
	__mapper_args__ = {
		"polymorphic_identity": __tablename__ # Refers to the attribute/column with that name
	}
	id: Mapped[primary_key] = mapped_column(ForeignKey(ClickEvent.id))

	switchID: Mapped[int]

	def __init__(self,
			clientTime: int | None,
			serverTime: int,
			pseudonym: str,
			phase: str,
			level: tuple[LevelType, str] | None,
			levelState: LevelState,
			switchID: int
		) -> None:

		super().__init__(
			clientTime=clientTime,
			serverTime=serverTime,
			pseudonym=pseudonym,
			phase=phase,
			level=level,
			object=ClickableObjects.SWITCH
		)
		
		self.levelState = levelState
		self.switchID = switchID


class ConfirmClickEvent(ClickEvent):
	""""""
	__tablename__ = "event_click_confirm"
	__mapper_args__ = {
		"polymorphic_identity": __tablename__ # Refers to the attribute/column with that name
	}
	id: Mapped[primary_key] = mapped_column(ForeignKey(ClickEvent.id))
	user: Mapped[bool]

	def __init__(self,
			clientTime: int | None,
			serverTime: int,
			pseudonym: str,
			phase: str,
			level: tuple[LevelType, str],
			levelState: LevelState,
			user: bool # true if the event comes from direct user interaction
		) -> None:

		super().__init__(
			clientTime=clientTime,
			serverTime=serverTime,
			pseudonym=pseudonym,
			phase=phase,
			level=level,
			object=ClickableObjects.CONFIRM
		)

		self.levelState = levelState
		self.user = user


class SimulateEvent(ClickEvent):
	""""""
	__tablename__ = "event_click_simulate"
	__mapper_args__ = {
		"polymorphic_identity": __tablename__ # Refers to the attribute/column with that name
	}
	id: Mapped[primary_key] = mapped_column(ForeignKey(ClickEvent.id))

	showPower: Mapped[bool]

	def __init__(self,
			clientTime: int | None,
			serverTime: int,
			pseudonym: str,
			phase: str,
			level: tuple[LevelType, str],
			showPower: bool
		) -> None:

		super().__init__(
			clientTime=clientTime,
			serverTime=serverTime,
			pseudonym=pseudonym,
			phase=phase,
			level=level,
			object=ClickableObjects.SIMULATE
		)
		self.consequenceEvent = "Show power" if showPower else "Hide power"
		self.showPower = False


class IntroNavigationEvent(ClickEvent):
	""""""
	__tablename__ = "click_event_navigation"
	__mapper_args__ = {
		"polymorphic_identity": __tablename__ # Refers to the attribute/column with that name
	}
	id: Mapped[primary_key] = mapped_column(ForeignKey(ClickEvent.id))
	
	currentSlide: Mapped[int]
	isChallenge: Mapped[bool]
	label: Mapped[str]
	delta: Mapped[int]

	def __init__(self,
			clientTime: int | None,
			serverTime: int,
			pseudonym: str,
			phase: str,
			currentSlide: int,
			isChallenge: bool,
			label: str,
			delta: int
		) -> None:

		super().__init__(
			clientTime=clientTime,
			serverTime=serverTime,
			pseudonym=pseudonym,
			phase=phase,
			level=None,
			object=ClickableObjects.ARROW
		)

		self.currentSlide = currentSlide
		self.isChallenge = isChallenge
		self.label = label
		self.delta = delta


class SelectDrawToolEvent(ClickEvent):
	""""""
	__tablename__ = "event_select_draw"
	__mapper_args__ = {
		"polymorphic_identity": __tablename__ # Refers to the attribute/column with that name
	}
	id: Mapped[primary_key] = mapped_column(ForeignKey(ClickEvent.id))

	def __init__(self,
			clientTime: int | None,
			serverTime: int,
			pseudonym: str,
			phase: str,
			level: tuple[LevelType, str],
			object: str
		) -> None:

		super().__init__(
			clientTime=clientTime,
			serverTime=serverTime,
			pseudonym=pseudonym,
			phase=phase,
			level=level,
			object=object
		)


class DrawEvent(LogEventLevel):
	"""Called after the player lifts the pen, eraser or delete button. 
	At this moment the screenshot of the canvas will be generated.
	"""
	__tablename__ = "event_draw"
	__mapper_args__ = {
		"polymorphic_identity": __tablename__ # Refers to the attribute/column with that name
	}
	id: Mapped[primary_key] = mapped_column(ForeignKey(LogEventLevel.id))

	tool: Mapped[str] = mapped_column(String(6))
	color: Mapped[int] = mapped_column(SmallInteger)

	def __init__(self,
			clientTime: int | None,
			serverTime: int,
			pseudonym: str,
			phase: str,
			level: tuple[LevelType, str] | None,
			tool: str,
			info: str
		) -> None:

		super().__init__(
			clientTime=clientTime,
			serverTime=serverTime,
			pseudonym=pseudonym,
			phase=phase,
			level=level
		)

		self.tool = tool
		self.color = int(info) if tool == 'pen' else 0


class PopUpEvent(LogEventLevel):
	""""""
	__tablename__ = "event_popup"
	__mapper_args__ = {
		"polymorphic_identity": __tablename__ # Refers to the attribute/column with that name
	}
	id: Mapped[primary_key] = mapped_column(ForeignKey(LogEventLevel.id))

	dialogName: Mapped[str]
	action: Mapped[bool] # True when showing, false when hiding
	nmbrSwitchClicks: Mapped[Optional[int]]
	optimumSwitchClicks: Mapped[Optional[int]]
	nmbrConfirmClicks: Mapped[Optional[int]]
	secondsRemaining: Mapped[Optional[int]]

	def __init__(self,
			clientTime: int | None,
			serverTime: int,
			pseudonym: str,
			phase: str,
			level: tuple[LevelType, str],
			dialogName: str,
			action: bool,
			*,
			nmbrSwitchClicks: Optional[int] = None,
			optimumSwitchClicks: Optional[int] = None,
			nmbrConfirmClicks: Optional[int] = None,
			secondsRemaining: Optional[int] = None
		) -> None:

		super().__init__(
			clientTime=clientTime,
			serverTime=serverTime,
			pseudonym=pseudonym,
			phase=phase,
			level=level
		)
		LogEvent.event = EventType.PopUp
		self.dialogName = dialogName
		self.action = action

		self.nmbrSwitchClicks = nmbrSwitchClicks
		self.optimumSwitchClicks = optimumSwitchClicks
		self.nmbrConfirmClicks = nmbrConfirmClicks
		self.secondsRemaining = secondsRemaining

		if action == True: # If show dialog
			if dialogName == 'feedback':
				assert nmbrSwitchClicks is not None
				assert optimumSwitchClicks is not None
				assert nmbrConfirmClicks is not None
			elif dialogName == 'timeRemaining':
				assert secondsRemaining is not None


class AltTaskEvent(LogEventLevel):
	""""""
	__tablename__ = "event_alt_task"
	__mapper_args__ = {
		"polymorphic_identity": __tablename__ # Refers to the attribute/column with that name
	}
	id: Mapped[primary_key] = mapped_column(ForeignKey(LogEventLevel.id))

	PARAM_SIZE = 32

	param_key: Mapped[str] = mapped_column(String(PARAM_SIZE))
	param_val: Mapped[str] = mapped_column(String(PARAM_SIZE))

	def __init__(self,
			clientTime: int | None,
			serverTime: int,
			pseudonym: str,
			phase: str,
			level: tuple[LevelType, str],
			param_key: str,
			param_val: str
		) -> None:

		super().__init__(
			clientTime=clientTime, serverTime=serverTime,
			pseudonym=pseudonym,
			phase=phase, 
			level=level
		)
		self.param_key = param_key
		self.param_val = param_val
