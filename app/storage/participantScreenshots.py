from math import isnan
import os
from typing import Optional

from app.gameConfig import SCREENSHOT_EXTENSION
from app.utilsGame import safe_join

class ScreenshotWriter:
	screenshotFolder = "instance/statistics/canvasPics"

	@classmethod
	def getPath(cls, pseudonym: str, phaseName: str, levelName: Optional[str], phaseIdx: int) -> str:
		"""Generate the screenshot path for the specified player, phase and level combination.
		
		- ./statistics/canvasPics/{pseudonym}/{phaseID}_{phaseName}/
		- ./statistics/canvasPics/{pseudonym}/{phaseID}_{phaseName}/{levelName}
		"""
		assert len(pseudonym) > 0
		assert len(phaseName) > 0
		assert not isnan(phaseIdx) and phaseIdx > 0 
		
		segments = [pseudonym, str(phaseIdx) + "_" + phaseName]
		
		if levelName is not None and len(levelName) > 0:
			safeName = levelName.replace('/', '_')
			segments.append(safeName)

		path = safe_join(cls.screenshotFolder, *segments)
		return path


	@classmethod
	def writeScreenshot(cls, screenshotFolder: str, picNmbr: int, imgData: bytes):
		"""Write an image file to `screenshotFolder`. All necessary subfolders will be created.
		
		Will automatically increment the picNmbr if a file with that name already exists.
		"""
		assert not isnan(picNmbr) and picNmbr >= 0, "Assertion Failed: Invalid pic number"
		
		os.makedirs(screenshotFolder, exist_ok=True) # Passing a path that is too long might be undefined behavior
		imagePath: Optional[str] = None

		for i in range(0, 99):
			imagePath = safe_join(screenshotFolder, str(picNmbr + i) + SCREENSHOT_EXTENSION)

			# If filename already exists, continue to increment
			if os.path.exists(imagePath):
				continue
			
			# At this point we are sure there is no file with that name, so we can write our image
			with open(imagePath, 'xb') as f:
				f.write(imgData)
			return
