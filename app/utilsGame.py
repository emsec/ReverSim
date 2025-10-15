from datetime import datetime
from enum import StrEnum
import os
import subprocess
from typing import Any, List, Optional
from markupsafe import escape

import werkzeug.security as ws


def now() -> int:
	"""The current time for use in the log files.
	
	Precision: One thousands of a second aka millisecond
	"""
	return int(datetime.now().timestamp()*1000)


# returns lines of file in an array 
def getFileLines(basePath: str, fileName: str, encoding: str = 'UTF-8') -> List[List[str]]:
	"""Return the contents of the file in the base folder as a string array"""
	path = safe_join(basePath, fileName)

	# store file content in string
	with open(path, 'r', encoding=encoding) as file:
		fileContent = file.readlines()

		# delete empty lines
		fileContent = list(filter(None, fileContent))

		output: list[list[str]] = []
		for line in fileContent:
			splitted = [s.strip() for s in line.split(':', 1)]
			output.append(splitted)
		
	return output


def safe_join(directory: str, *pathNames: str) -> str:
	"""Wrapper for werkzeug.security.safe_join(), but always returns string and raises FileNotFoundError if the
	user specified path manages to escape the trusted parent folder.
	"""
	path = ws.safe_join(directory, *pathNames)
	if path is None:
		raise FileNotFoundError('safe_join() could not create a safe path')
	return path


def sanitizeString(unsafeText: Any) -> str:
	"""Sanitize user input by removing all HTML tags and unnecessary whitespaces to prevent Cross Site Scripting."""
	return str(escape(escape(unsafeText).striptags()))


def sanitizeString2(unsafeText: Optional[str]) -> Optional[str]:
	"""Same as `sanitizeString()`, but will pass trough None without converting it to a string."""
	if unsafeText is None:
		return None
	return sanitizeString(unsafeText)


# https://stackoverflow.com/questions/14989858/get-the-current-git-hash-in-a-python-script
def get_git_revision_hash(shortHash: bool = False) -> str:
	try:
		hash_env_name = 'GAME_GIT_HASH_SHORT' if shortHash else 'GAME_GIT_HASH'
		git_command = ['git', 'rev-parse', '--short', 'HEAD'] if shortHash else ['git', 'rev-parse', 'HEAD']

		# Try to read the Git Hash from an environment variable
		git_hash_env = os.getenv(hash_env_name)
		if git_hash_env is not None and git_hash_env.isalnum():
			return git_hash_env[:12]
		
		# Try to determine the commit hash with a command
		git_hash_command = subprocess.check_output(git_command).decode('ascii').strip()
		if not git_hash_command.isalnum():
			raise Exception("Git command returned invalid output")
		return git_hash_command
	except Exception:
		return "Unknown"


def getCircuitStatusLog(
		switchStates: dict[str, Any] | None,
		bulbStates: dict[str, Any] | None,
		dangerStates: dict[str, Any] | None,
		inverterStates: dict[str, Any] | None,
		andStates: dict[str, Any] | None,
		orStates: dict[str, Any] | None
	) -> str:
	"""Build a string listing the current state of all logic gates, inputs/outputs and switches. 
	
	Used to print the client state to the statistic logs	
	"""
	ELEMENTS = [
		("Switch_States [ID, click state, outputstate]", switchStates),
		("Bulb_States [ID, output state]", bulbStates),
		("DangerSign_States [ID, output state]", dangerStates),
		("Inverter_States [ID, output state]", inverterStates),
		("And-Gate_States [ID, output state]", andStates),
		("Or-Gate_States [ID, output state]", orStates),
	]

	assert isinstance(switchStates, dict), "Switches must not be empty"

	output: str = ""
	for desc, e in ELEMENTS:
		if not isinstance(e, dict) or len(e) < 1:
			continue

		output += '\n§' + desc + ': ' + gateStatesToString(e)

	return output


def gateStatesToString(gates: dict[str, int]) -> str:
	return ''.join([f'[{int(gateID)}, {int(state)}]' for gateID, state in gates.items()])


def getShortPseudo(pseudonym: str, length: int = 16) -> str:
	if len(pseudonym) > length:
		return pseudonym[:length] + "..."
	
	return pseudonym

X_TRUE: Any = [1, True,  '1', 'True',  'true', 'yes']
X_FALSE: Any = [0, False, '0', 'False', 'false', 'no']


class EventType(StrEnum):
	"""All event types that can be found in the player logfile `§Event: ...`"""
	TimeSync = "TimeSync"
	BackOnline = "Online after disconnection"
	StartSession = "Reconnect"
	SkillAssessment = "SkillAssessment"
	GroupAssignment = "Group Assignment"
	PhaseRequested = "change in Scene"
	PhaseStarted = "Loaded Phase"
	Click = "Click"
	LevelRequested = "new " #+ LevelType
	LevelStarted = "Loaded"
	QualiPassed = 'Passing ' #+ ParticipantLogger.getOrdinalNumber(lvlNo)
	QualiFailed = 'Failing ' #+ ParticipantLogger.getOrdinalNumber(lvlNo)
	PopUp = "Pop-Up displayed"
	Pen = "Used Pen"
	DrawingTool = "Used drawing tool"
	AltTask = "AltTask"
	Redirect = "Redirect"
	GameOver = "Game Over"
	CreatedLog = "Created Logfile"

# All events that are not initiated by a client and can therefore only use the server clock
ServerTimeEvents = [
	EventType.CreatedLog,
	EventType.SkillAssessment,
	EventType.Redirect,
	EventType.GroupAssignment,
	EventType.GameOver,
	#EventType.AltTask # NOTE You are responsible for proper client time in the AltTask
]

class PhaseType(StrEnum):
	"""All possible Phase types"""
	# Phase Type with level
	Quali = "Quali"
	Competition = "Competition"
	Skill = "Skill"
	AltTask = "Alternative"
	Editor = "LevelEditor"
	Viewer = "LevelViewer"

	# Normal phases
	Start = "GameIntro" # GameIntroND
	ElementIntro = "IntroduceElements"
	DrawTools = "IntroduceDrawingTools"
	FinalScene = "FinalScene" # FinalSceneNPS

	# Misc Phases
	Preload = "PreloadScene"
	NotStarted = 'not started' # 
	Finished = 'finished'
	

class LogKeys(StrEnum):
	"""An incomplete list of possible log file keys"""
	ORIGIN_LINE = '_originLine'
	TIME = 'Time' # Client time
	EVENT = 'Event'
	TIME_SERVER = 'Server'
	FILENAME = 'Filename'
	TYPE = 'Type'


class ClickableObjects(StrEnum):
	CONFIRM = "ConfirmButton"
	CONTINUE = "Continue Button"
	SIMULATE = "Simulate-Level Button"
	SWITCH = "Switch"
	ERASER = "Eraser"
	PEN = "Pen"
	DELETE = "Delete Button"
	PEN_RED = "Red"
	PEN_GREEN = "Green"
	PEN_BLUE = "Blue"
	ARROW = "Arrow" # In IntroduceElements
	SKIP = "Skip-Level Button"


class LevelType(StrEnum):
	INFO = 'info'
	LEVEL = 'level'
	URL = 'url'
	IFRAME = 'iframe'
	TUTORIAL = 'tutorial'
	LOCAL_LEVEL = 'localLevel'
	SPECIAL = 'special'


class IntroLabels(StrEnum):
	slide01 = 'batteryDesc'
	slide02 = 'wireDesc'
	slide03 = 'switchDesc'
	slide04 = 'bulbDesc'
	slide05 = 'instructionBulbChallenge'
	slide06 = 'dangerSignDesc'
	slide07 = 'instructionDangerSignChallenge'
	slide08 = 'inverterDesc'
	slide09 = 'instructionInverterChallenge'
	slide10 = 'orGateDesc'
	slide11 = 'instructionOrGateChallenge'
	slide12 = 'andGateDesc'
	slide13 = 'instructionAndGateChallenge'
	slide14 = 'splitterDesc'
	slide15 = 'instructionSplitterChallenge'
	slide16 = 'endElementIntroText'


# Type aliases to clarify, which timestamps are in client time and which are in server time
ClientTime = int
ServerTime = int


# +-------------------------------+
# |       Markdown Utils          |
# --------------------------------+

GFM_PARENTHESES = ['(', ')']
GFM_BRACKETS = [*GFM_PARENTHESES, '[', ']', '{', '}']
GFM_POINTY_BRACKETS = ['<', '>']
GFM_DASHES = ['-', '_']
GFM_PUNCTUATION = ['!', '"', '#', '$', '%', '&', "'", '*', '+', 
	',', '.', '/', ':', ';', '=', '?', '@', '\\', '^',
	'`', '|', '~', *GFM_BRACKETS, *GFM_POINTY_BRACKETS
]

GFM_BACKSLASH_ESCAPES = [*GFM_PUNCTUATION, *GFM_DASHES]


def gfmSanitizeLinkText(text: str) -> str:
	"""Sanitize text to be included as a link text or as an image description.

	Relevant section in the GitHub Flavored Markdown specification:
	- https://github.github.com/gfm/#link-text (page might be slow to render)
	"""
	for ch in GFM_BRACKETS:
		if ch in text:
			text = text.replace(ch, '\\' + ch)

	return text


def gfmTitleToFragment(title: str) -> str:
	"""GitHub automatically creates fragment links to each heading.
	
	Relevant section of the GitHub Flavored Markdown specification:
	- https://github.github.com/gfm/#backslash-escapes
	- https://pandoc.org/MANUAL.html#extension-gfm_auto_identifiers
	"""
	title = title.lower().strip()
	
	title = title.replace(' ', '-')

	for ch in GFM_PUNCTUATION:
		if ch in title:
			title = title.replace(ch, '')
	
	return '#' + title


def gfmSanitizeTable(td: str) -> str:
	"""Sanitize content to be included inside a gfm table cell.
	
	Block-level elements are also not allowed, but they are not checked!

	Relevant section in the GitHub Flavored Markdown specification:
	- https://github.github.com/gfm/#table
	"""
	return td.replace('|', '\\|')


def gfmSanitizeLink(link: str) -> str:
	"""Make links safe to be used inside gfm.
	
	Relevant section in the GitHub Flavored Markdown specification:
	- https://github.github.com/gfm/#links
	- https://github.github.com/gfm/#images
	"""
	assert '\n' not in link, "Links can't contain line breaks"

	for ch in GFM_POINTY_BRACKETS:
		if ch in link:
			link = link.replace(ch, '\\' + ch)

	if ' ' in link:
		return '<' + link + '>'
	else:
		return link
