import functools
from typing import Any, Dict
from app.gameConfig import GameConfig

# Compatibility layer for the game code which was designed for a gameConfig in a module.
# This creates a singleton and exposes the class methods of the new gameConfig on
# module level

__gameConfig: GameConfig|None = None


def loadGameConfig(configName: str = "conf/gameConfig.json", instanceFolder: str = 'instance'):
	"""
	Load the gameConfig in the singleton of this module
	
	:param configName: the path of the gameConfig.json relative to the `instanceFolder`
	:param instanceFolder: the instance folder where config files and statistics are stored
	"""
	global __gameConfig
	__gameConfig = GameConfig(instanceFolder=instanceFolder, configName=configName)


def setGameConfig(config: GameConfig):
	global __gameConfig
	__gameConfig = config


@functools.wraps(GameConfig.groups)
def groups() -> Dict[str, Any]:
	assert __gameConfig is not None
	return	__gameConfig.groups()


@functools.wraps(GameConfig.get)
def get(key: str) -> Dict[str, Any]:
	assert __gameConfig is not None
	return __gameConfig.get(key)


@functools.wraps(GameConfig.config)
def config(key: str, default: Any):
	assert __gameConfig is not None
	return __gameConfig.config(key, default)


@functools.wraps(GameConfig.getInt)
def getInt(key: str) -> int:
	assert __gameConfig is not None
	return __gameConfig.getInt(key)


@functools.wraps(GameConfig.getGroup)
def getGroup(group: str) -> Dict[str, Any]:
	assert __gameConfig is not None
	return __gameConfig.getGroup(group)


@functools.wraps(GameConfig.getDefaultLang)
def getDefaultLang() -> str:
	assert __gameConfig is not None
	return __gameConfig.getDefaultLang()


@functools.wraps(GameConfig.getFooter)
def getFooter() -> Dict[str, str]:
	assert __gameConfig is not None
	return __gameConfig.getFooter()


@functools.wraps(GameConfig.getGitHash)
def getGitHash() -> str:
	assert __gameConfig is not None
	return __gameConfig.getGitHash()


@functools.wraps(GameConfig.getGroupsDisabledErrorLogging)
def getGroupsDisabledErrorLogging() -> list[str]:
	assert __gameConfig is not None
	return __gameConfig.getGroupsDisabledErrorLogging()


@functools.wraps(GameConfig.getAssetPath)
def getAssetPath() -> str:
	assert __gameConfig is not None
	return __gameConfig.getAssetPath()


@functools.wraps(GameConfig.isLoggingEnabled)
def isLoggingEnabled(group: str) -> bool:
	assert __gameConfig is not None
	return __gameConfig.isLoggingEnabled(group)
