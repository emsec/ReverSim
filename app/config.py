from json import JSONDecodeError
import logging
from typing import Any, Dict, Optional, Union
from flask import json

from app.utilsGame import LevelType, PhaseType, get_git_revision_hash, safe_join

# USAGE : `import config`

# CONFIG: The config was moved to gameConfig.json
# 
# Please note: the debug prefix is now automatically handled and doesn't have to be declared manually down below 
# (e.g. debugLow as the debug group for low does not have to be configured)
# 
# Group names are case insensitive. They will always be converted to lower case internally (however you should use lower case for group names in the config!)

# CONFIG Current Log File Version
# 1.Milestone.Subversion
LOGFILE_VERSION = "2.0.4"

PSEUDONYM_LENGTH = 32
LEVEL_ENCODING = 'UTF-8' # was Windows-1252
TIME_DRIFT_THRESHOLD = 200 # ms
STALE_LOGFILE_TIME = 48 * 60 * 60 # close logfiles after 48h
MAX_ERROR_LOGS_PER_PLAYER = 25

# Number of seconds, after which the player is considered disconnected. A "Back Online"
# message will be printed to the log, if the player connects afterwards. Also used for the
# Prometheus Online Player Count metric
BACK_ONLINE_THRESHOLD_S = 5.0 # [s]

# The interval at which prometheus metrics without an event source shall be updated
METRIC_UPDATE_INTERVAL = 1 # [s]

# NOTE: This is used when the client needs to request assets from the server. If you need
# the server side asset folder, use gameConfig.getAssetPath()
REVERSIM_STATIC_URL = "/assets"

class GroupNotFound(Exception):
	"""Raised when a group is requested, which is not in the config"""
	pass


__configStorage : Dict[str, Any] = {
	"gitHash": "!Placeholder, config is unloaded!",
	"assetPath": "instance/conf/assets",
	"languages": ["en"],
	"author": "!Placeholder, config is unloaded!",
	"crashReportLevel": 2,
	"crashReportBlacklist": [],
	"groupIndex": {
		"enabled": True,
		"showDebug": True,
		"footer": "Your Institution | 20XX",
	},
	"footer": {
		"imprint": ".",
		"privacyProtection": ".",
		"researchInfo": "."
	},
	"gamerules": {},
	"groups": {},
} # mockup for the editor autocompletion, this will be overridden with the config loaded from disk

__instance_folder: Optional[str] = None

def getDefaultGamerules() -> dict[str, Optional[Union[str, int, bool, dict[str, Any]]]]:
	return {
		"enableLogging": True,
		"showHelp": True, # Used when the ingame help feature gets implemented in the future
		"insertTutorials": True, # Automagically insert the tutorial slides for covert and camouflage gates
		"scoreValues": {
			"startValue": 100,
			"minimumScore": 0,
			"switchClick": 0,
			"simulate": -10,
			"wrongSolution": -10,
			"correctSolution": 0,
			"penaltyMultiplier": 1
		},
		"phaseDifficulty": {
			"Quali": "MEDIUM",
			"Competition": "MEDIUM",
			"Skill": "MEDIUM"
		},
		"reminderTime": 15,
		"mediumShowSimulateButton": False,
		"skillShowSkipButton": "never", # 'always', 'never' or 'struggling'
		"competitionShowSkipButton": "struggling",
		"wrongSolutionCooldown": 2,
		"wrongSolutionCooldownLimit": 0,
		"wrongSolutionMultiplier": 1,
		"tutorialAllowSkip": 'yes', # 'yes', 'no' or 'always'
		"simulationAllowAnnotate": True,

		"textPostSurveyNotice": "postSurvey",
		
		"allowRepetition": False,

		"footer": getFooter(),

		"urlPreSurvey": None,
		"urlPostSurvey": None,
		"disclaimer": REVERSIM_STATIC_URL + "/researchInfo/disclaimer_{lang}.html",
		"hide": False,
	}

# Default gamerules, will be overridden by the gamerules defined inside the group
gameruleDefault = None


def loadConfig(configName: str = "conf/gameConfig.json", instanceFolder: str = 'instance'):
	"""Read gameConfig.json into the config variable"""
	global __configStorage, __instance_folder
	__instance_folder = instanceFolder

	# load the config (groups, gamerules etc.)
	try:
		configPath = safe_join(instanceFolder, configName)
		with open(configPath, "r", encoding="utf-8") as f:
			# Load Config file & fill default gamerules
			logging.info('Loading config "' + configPath + '"...')
			__configStorage = json.load(f)
			gameruleDefault = getDefaultGamerules()

			# Get Git Hash from Config
			__configStorage['gitHash'] = get_git_revision_hash(shortHash=True)
			logging.info("Game Version: " + LOGFILE_VERSION + "-" + getGitHash())

		# Validate and initialize all groups / add default gamerule
		for g in __configStorage['groups']:
			# Warn the user, if there is an uppercase group
			if g != g.casefold():
				logging.warning("The group name \""+ g + "\" in the config is not in lower case!")

			# The group has the gamerule attribute, try to merge it with the default
			if 'config' in __configStorage['groups'][g]:
				gamerules = __configStorage['groups'][g]['config']

				# check if the gamerule actually exists
				if gamerules in __configStorage['gamerules']:
					gamerule = __configStorage['gamerules'][gamerules]
					__configStorage['groups'][g]['config'] = {**gameruleDefault, **gamerule}
				else:
					__configStorage['groups'][g]['config'] = gameruleDefault
					logging.warning("Failed to find the gamerule " + gamerules + " for group " + g + ", using the default one instead.")

			# No gamerule attribute is present for this group, using the default one
			else:
				gamerules = 'DEFAULT'
				__configStorage['groups'][g]['config'] = gameruleDefault


		# Second pass to run validation (the gamerules are now initialized and stored under `currentGroup['config']`)
		for g in __configStorage['groups']:
			gamerules = __configStorage['groups'][g]['config']
			# Validate pause timer
			if TIMER_NAME_PAUSE in __configStorage['groups'][g]['config']:
				validatePauseTimer(g, gamerules)

			if TIMER_NAME_GLOBAL_LIMIT in __configStorage['groups'][g]['config']:
				validateGlobalTimer(g, gamerules, TIMER_NAME_GLOBAL_LIMIT)
			
			# Validate skill sub-groups gamerules are the same as origin gamerules
			if PhaseType.Skill in __configStorage['groups'][g]:
				validateSkillGroup(g)

			# Make sure the error report level is set
			if 'crashReportLevel' not in __configStorage:
				logging.warning("Missing config entry crashReportLevel, assuming 2!")
				__configStorage['crashReportLevel'] = 2

		# Loading finished successfully, print log
		logging.info("Config: Loaded " + str(len(__configStorage['groups'])) + " groups and " + str(len(__configStorage['gamerules'])) + " gamerules")

	except JSONDecodeError as e:
		logging.exception("Syntax error in " + configName + ": \n \"" + str(e) + "\"\n")
		raise SystemExit

	except AttributeError as e:
		logging.exception("An important item is missing in " + configName + ": \n \"" + str(e) + "\"\n")
		raise SystemExit

	except OSError as e:
		logging.exception("Failed to load gameConfig.json: \n \"" + str(e) + "\"\n")
		raise SystemExit

	except AssertionError as e:
		logging.exception("Gamerule: " + str(e))
		raise SystemExit


	except Exception as e:
		raise e

def validatePauseTimer(group: str, gameruleName: str):
	P_CONF = __configStorage['groups'][group]['config'][TIMER_NAME_PAUSE]
	assert 'duration' in P_CONF and P_CONF['duration'] >= 0, 'Invalid pause duration in "' + gameruleName + '"'
	return validateGlobalTimer(group, gameruleName, TIMER_NAME_PAUSE)


def validateGlobalTimer(group: str, gameruleName: str, timerName: str):
	P_CONF = __configStorage['groups'][group]['config'][timerName]
	assert 'after' in P_CONF and P_CONF['after'] >= 0, 'Invalid pause timer start value in "' + gameruleName + '"'
	
	assert P_CONF['startEvent'] in [*PHASES, None], 'Invalid start event specified "' + gameruleName + '"'


def validateSkillGroup(group: str):
	"""Make sure that gamerules of the SkillAssessment sub-groups matches the origin gamerules"""
	originGamerules: Dict[str, Any] = __configStorage['groups'][group]['config']

	# Loop over all groups the player can be assigned to after the Skill assessment
	for subGroup in __configStorage['groups'][group][PhaseType.Skill]['groups'].keys():
		# Make sure the sub-group gamerules key&values match the parents gamerules
		# Debug: [(str(k), originGamerules.get(k) == v) for k, v in subGamerules.items()]
		subGamerules: Dict[str, Any] = __configStorage['groups'][subGroup]['config']
		if not all((originGamerules.get(k) == v for k, v in subGamerules.items())):
			logging.warning("The gamerules of the sub-groups specified for SkillAssessment should match the origin gamerules" \
					+ " (" + group + " -> " + subGroup + ")!"
			)


def config(key: str, default: Any):
	"""Get a key from the config. This might be another dict.

	Have to resort to a getter because pythons `import from` is stupid
	https://stackoverflow.com/questions/15959534/visibility-of-global-variables-in-imported-modules
	"""
	return __configStorage.get(key, default)


def get(key: str) -> Dict[str, Any]:
	"""Get a key from the config. This might be another dict. Throws an exception, if the key is not found"""
	return __configStorage[key]


def getInt(key: str) -> int:
	assert isinstance(__configStorage[key], int), 'The config key is not of type int!'
	return __configStorage[key]


def groups() -> Dict[str, Any]:
	"""Shorthand for `config.get('groups')`"""
	return __configStorage['groups']


def getGroup(group: str) -> Dict[str, Any]:
	"""Shorthand for `config.get('groups')[group]`"""
	try:
		return __configStorage['groups'][group]
	except KeyError:
		raise GroupNotFound("Could not find the requested group '" + group + "'!")
	

def getDefaultLang() -> str:
	"""Get the default language configured for this game. 
	
	The first language in the `languages` array in the config is chosen.
	"""
	return __configStorage["languages"][0]


def getFooter() -> Dict[str, str]:
	"""Get the footer from the config or return the Default Footer if none is specified"""
	DEFAULT_FOOTER = {
		"researchInfo": REVERSIM_STATIC_URL + "/researchInfo/researchInfo.html"
	}	
	return config('footer', DEFAULT_FOOTER)


def getInstanceFolder() -> str:
	"""The Flask instance folder where the customizable and runtime data lives.
	
	Defaults to ./instance for local deployments and /usr/var/reversim-instance for the
	Docker container.
	"""
	if __instance_folder is None:
		raise RuntimeError("Tried to access the instance folder but it is still none. Was createApp() ever called?")
	
	return __instance_folder


def getAssetPath() -> str:
	"""Get the base path for assets like levels, info screens, languageLib, user css etc."""
	return safe_join(getInstanceFolder(), config('assetPath', 'conf/assets'))


def isLoggingEnabled(group: str) -> bool:
	return getGroup(group)['config'].get('enableLogging', True)


def getGitHash() -> str:
	"""Get the git hash that was determined by a call to `get_git_revision_hash(true)` while the config was loaded."""
	return __configStorage['gitHash']


def getGroupsDisabledErrorLogging() -> list[str]:
	"""Get a list of all groups with disabled error logging. 
	
	- `crashReportBlacklist` if the lists exists in the config and it is not empty
	- otherwise all groups witch gamerule setting `enableLogging` = `False`
	"""
	if 'crashReportBlacklist' in __configStorage and len(__configStorage['crashReportBlacklist']) > 0:
		return __configStorage['crashReportBlacklist']
	else:
		return [
			name for name, conf in __configStorage['groups'].items() if not conf['config']['enableLogging']
		]


def getLevelList(name: str):
	"""Get a level list in the new format"""
	try:
		return __configStorage['levels'][name]
	except KeyError:
		raise GroupNotFound("Could not find the level list with name '" + name + "'!")
	

#########################
#   Phase Constants     #
#########################

# All phases that will load levels from the server
PHASES_WITH_LEVELS = [PhaseType.Quali, PhaseType.Competition, PhaseType.Skill, PhaseType.AltTask, PhaseType.Editor]

PHASES = [*PHASES_WITH_LEVELS, PhaseType.Start, PhaseType.ElementIntro, PhaseType.DrawTools, PhaseType.FinalScene, PhaseType.Viewer]


#########################
#   Level Constants     #
#########################

# All types that will be send to the server and their corresponding log file entry
ALL_LEVEL_TYPES: dict[str, str] = {
	LevelType.INFO: 'Info',
	LevelType.LEVEL: 'Level', 
	LevelType.URL: 'AltTask', 
	LevelType.IFRAME: 'AltTask',
	LevelType.TUTORIAL: 'Tutorial',
	LevelType.LOCAL_LEVEL: 'LocalLevel',
	LevelType.SPECIAL: 'Special'
}

# NOTE Special case: 'text' is written in the level list, but 'info' is send to the server, 
# see doc/Overview.md#levels-info-screens-etc
REMAP_LEVEL_TYPES = {
	'text': LevelType.INFO
}

# The new types for the Alternative Task shall also be treated as levels aka tasks
LEVEL_FILETYPES_WITH_TASK = [LevelType.LEVEL, LevelType.URL, LevelType.IFRAME]

LEVEL_BASE_FOLDER = 'levels'
LEVEL_FILE_PATHS: dict[str, str] = {
	LevelType.LEVEL: 		LEVEL_BASE_FOLDER + '/differentComplexityLevels/',
	LevelType.INFO: 		LEVEL_BASE_FOLDER + '/infoPanel/',
	LevelType.TUTORIAL: 	LEVEL_BASE_FOLDER + '/elementIntroduction/',
	LevelType.SPECIAL: 		LEVEL_BASE_FOLDER + '/special/'
}

# config name for the pause timer
TIMER_NAME_PAUSE = 'pause'
DEFAULT_PAUSE_SLIDE = 'pause.txt'

# 
TIMER_NAME_GLOBAL_LIMIT = 'timeLimit'
