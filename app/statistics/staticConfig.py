# Configure Options for the CSV
from enum import Enum
from typing import Any, Dict, TypeAlias, cast

from app.utilsGame import EventType, PhaseType

# Type hint for a Log event
EVENT_T: TypeAlias = Dict[str, Any]

# Enable special cases for legacy Logfiles
ENABLE_SPECIAL_CASES = False

# Max Logfile Size in Bytes (Currently 20MB)
MAX_LOGFILE_SIZE = 1024 * 1024 * 20

TABLE_DELIMITER = ","
TABLE_TRUE = "Yes"
TABLE_FALSE = "No"
TABLE_NAN = "NaN"
TABLE_UNDEFINED = "### error in statistics.py script!!! ###"

class LevelStatus(Enum):
	"""Values for LEVEL_SOLVED"""
	ABORTED 	= "Aborted" 		# The user stopped playing while solving the level 
	NOTREACHED 	= "Never reached"	# All levels after STATUS_ABORTED
	SKIPPED 	= "Skipped" 		# The user used the skip level button
	FAILED 		= "Failed" 			# The user was thrown back to Training Phase
	SOLVED 		= "Solved" 			# The level is solved
	NOTSTARTED 	= "Not started"		# The user loaded the level but didn't make any interactions
	INPROGRESS 	= "In Progress"		# The level is currently being solved. Should never end up in the CSV, only used internally
	LOADED      = "Loaded"			# The level was loaded but the player did not interact with anything yet
	RELOADED	= "Aborted RL"		# Aborted due to Page Reload


class PhaseStatus(Enum):
	"""Values for Phase Solved"""
	ABORTED 	= "Aborted" 		# The user stopped playing while solving the level 
	NOTREACHED 	= "Never reached"	# All levels after STATUS_ABORTED
	FAILED 		= "Failed" 			# The user was thrown back to Training Phase
	SOLVED 		= "Solved" 			# The level is solved
	NOTSTARTED 	= "Not started"		# The user loaded the level but didn't make any interactions
	INPROGRESS 	= "In Progress"		# For now STATUS_ABORTED is also used when level is in progress

class TableHeader(Enum):
	"""Names that are used to generate the table header inside the csv."""
	GENERAL_UI					= "UI"
	GENERAL_COMPLEXITY			= "Complexity"
	GENERAL_TRAINING			= "Started training phase"
	GENERAL_QUALIFICATION		= "Started qualification phase"
	GENERAL_COMPETITION			= "Started competition phase"
	GENERAL_FINAL_SCENE			= "Got to final scene"
	GENERAL_QUALI_ITERATIONS	= "Iterations of quali phases"
	GENERAL_ISDEBUGGROUP		= "Is in Debug Group"
	TIME_TRAINING				= "Time Training"
	TIME_QUALIFICATION			= "Time Quali"
	TIME_COMPETITION			= "Time Competition"
	TIME_TOTAL					= "Time Total"

class TableHeaderLevel(Enum):
	"""Names that are used to generate the table header for each level inside the csv."""
	SOLVED				= "Level status"
	N_SWITCH_CLICKS		= "Number of switch clicks"
	N_CONFIRM_CLICKS	= "Number of confirm clicks"
	TIME_SPENT			= "Time spent"
	TIME_FIRST_TRY		= "Time spent first try"
	EFFICIENCY_SCORE	= "Efficiency score"
	ESCORE_FIRST_TRY	= "Efficiency score first try"
	MIN_SWITCH_CLICKS	= "Minimum switch clicks"
	POSITION			= "Level position"
	DRAW_TOOLS			= "Used Drawingtool"

class EventNames(Enum):
	GROUP_ASSIGNMENT		= {"Event": EventType.GroupAssignment}
	REDIRECT				= {"Event": EventType.Redirect}
	GAME_LOADED				= {"Event": EventType.PhaseRequested, "Scene": "PreloadScene"} # type: ignore
	CHANGE_SCENE			= {"Event": EventType.PhaseRequested}
	DRAWTOOLS_PEN			= {"Event": EventType.Pen}
	DRAWTOOLS_ERASER		= {"Event": EventType.DrawingTool, "Tool": "eraser"} # type: ignore
	DRAWTOOLS_DELETE		= {"Event": EventType.DrawingTool, "Tool": "delete button"} # type: ignore
	CLICK_SWITCH			= {"Event": EventType.Click, "Object": "Switch"} # type: ignore
	CLICK_CONFIRM			= {"Event": EventType.Click, "Object": "ConfirmButton"} # type: ignore
	CLICK_NEXT				= {"Event": EventType.Click, "Object": "Continue Button"} # type: ignore
	CLICK_SIMULATE			= {"Event": EventType.Click, "Object": "Simulate-Level Button"} # type: ignore
	CLICK_INTRO_ARROW		= {"Event": EventType.Click, "Object": "Arrow"} # type: ignore
	LOAD_INFO				= {"Event": EventType.LevelRequested + " Info"}
	LOAD_LEVEL				= {"Event": EventType.LevelRequested + " Level"}
	LOAD_SPECIAL			= {"Event": EventType.LevelRequested + " Special"}
	# There might be more LOAD_ events, they all start with new ...
	STARTED					= {"Event": EventType.LevelStarted} # NOTE LOAD_FINISHED, Called when the level is started
	POPUP_CLICK_FEEDBACK	= {"Event": EventType.PopUp, "Content": "Feedback about Clicks"} # type: ignore
	SKILL_ASSESSMENT		= {"Event": EventType.SkillAssessment}
	ALT_TASK				= {"Event": EventType.AltTask}
	TIME_SYNC				= {"Event": EventType.TimeSync}
	CLICK_SKIP				= {"Event": EventType.Click, "Object": "Skip-Level Button", "Consequence Event": "Current level is being skipped"} # type: ignore

	def items(self):
		"""Shorthand for `self.value.items()`"""
		return cast(dict[str, EventType|str], self.value).items() # type: ignore

GAME_INTRO_PHASES: list[str] = [PhaseType.Start, 'GameIntroND']
