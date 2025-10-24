import logging
import random
from app.config import ALL_LEVEL_TYPES, LEVEL_ENCODING
from app.model.Level import Level
from app.model.LevelLoader.LevelLoader import LevelLoader
from app.utilsGame import LevelType, getFileLines


class TextFileLevelLoader(LevelLoader):
	def loadLevels(self) -> list[Level]:
		self._levels = []
		
		# Get the file names of the level list and make sure this is an array, even if 
		# array contains only one entry
		levelLists: str|list[str] = self._phaseConfig['levels']
		if not isinstance(levelLists, list):
			levelLists = [levelLists]

		for ll in levelLists:
			self.__readLevelList(
				fileName=ll,
				shuffle=self._phaseConfig.get('shuffle', False), # true | false
			)

		assert self._levels is not None and len(self._levels) > 0, "No levels have been loaded, this is probably an error"
		return self._levels


	def __readLevelList(self, fileName: str, shuffle: bool) -> None:
		"""Utility function used by loadLevels(), read a level list and add all levels to the que"""
		# get file content for the group the participant is in
		fileContent = getFileLines(Level.getBasePath('levelList'), fileName, encoding=LEVEL_ENCODING)
		fileTypes: list[str] = []
		levelFileNames: list[str] = [] # These might get shuffled if enabled in the config
		infoPanelFileNames: list[str] = [] # These will not be shuffled

		# fill arrays
		for fileData in fileContent:
			levelType, name = fileData
			
			# Append Level
			if levelType == LevelType.LEVEL:
				# If level info is not found in cache, read the level file
				if name not in Level.levelCache:
					try: 
						Level.levelCache[name] = self.generateCacheEntry(levelType, name)

					except Exception as e:
						logging.error("Exception while generating level cache: " + str(e))
				
				# Add level
				levelFileNames.append(name)
				fileTypes.append(levelType)

			# Append Info Panel
			elif levelType in ['text', LevelType.INFO]: # NOTE: text is used for legacy reasons
				infoPanelFileNames.append(name)
				fileTypes.append(levelType)			

			# Add other stuff, like Tutorial slides or AltTask
			elif levelType in ALL_LEVEL_TYPES.keys():
				infoPanelFileNames.append(name)
				fileTypes.append(levelType)

		# Randomize / shuffle the level file names if configured 
		if shuffle:
			random.shuffle(levelFileNames)

		# Feed the parsed entries into the new level que system
		for ft in fileTypes:
			fileName = levelFileNames.pop(0) if ft == LevelType.LEVEL else infoPanelFileNames.pop(0)
			self._appendLevel(slideType=ft, fileName=fileName)
