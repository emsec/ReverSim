import importlib
from typing import Any, Callable, Dict, List, Tuple

from app.statistics.statsPhase import StatsPhase


# ----------------------------------------
#              Alt Tasks
# ----------------------------------------
class AltTaskParser():
	def handleAltEvent(self, e: Dict[str, Any]):
		"""Override this method to sort the AltTask methods to your own implemented handlers. 
		The event will always look similar to the event below:
		
		```
		Time: 1705597257633
		§Event: AltTask
		§Payload Key: Payload Value
		```
		"""
		pass


	def generateAltTaskLevels(self, levelType: str) -> List[Tuple[str, str]]:
		"""A level with type `url` or `iframe` will always be added to the level outline, 
		however your AltTask may introduce own levels, these can be generated with this method.
		"""
		return []


	@staticmethod
	def factory(taskName: str):
		# TODO Add dynamic loading of different ZVT implementations
		packages = taskName.split('.')
		AltTask = getattr(importlib.import_module('.'.join(packages[0:-1])), packages[-1])

		assert isinstance(AltTask, type(AltTaskParser))
		assert isinstance(AltTask, type(StatsPhase))
		return AltTask
