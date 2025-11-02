import os
from typing import NamedTuple

import app.config as gameConfig
from app.model.Level import LEVEL_FILE_PATHS
from app.model.Phase import PHASES_WITH_LEVELS

canvas_offset = (0, 167)

canvas_size = (1280,720)

# levels have fixed storage size, but are downscaled for display to fit the
# canvas with the margins below
LEVEL_SIZE = (1280,720)
LEVEL_MARGINS = {
	"left": 70,
	"right": 0,
	"top": 0,
	"bottom": 25
}

# ---
level_w, level_h = LEVEL_SIZE
canvas_w, canvas_h = canvas_size

xmin = LEVEL_MARGINS["left"]
xmax = canvas_w-LEVEL_MARGINS["right"]
ymin = LEVEL_MARGINS["top"]
ymax = canvas_h-LEVEL_MARGINS["bottom"]

level_scaled_w = xmax-xmin
level_scaled_h = ymax-ymin
# ---

ELEMENT_SIZES: dict[str, tuple[int, int]] = {
	# created manually by looking at image files in game server, assuming scale factor 1
	"VCC": (50,26),
	"GND": (50,26),
	"Switch": (50,23), # NOTE open/closed are differently sized
	"DangerSign": (43,50),
	"LightBulb": (45,30),
	"AndGate": (38,50),
	"OrGate": (49,50),
	"Inverter": (42,40),
	"Splitter": (8,8),
	"CovertGate": (50,50), # NOTE might need splitting in OR/AND
}

ELEMENT_TYPES = {
	'VCC': 'VCC',
	'GND': 'GND',
	'Switch': 'SWITCH',
	'DangerSign': 'OUT',
	'LightBulb': 'OUT',
	'AndGate': 'AND',
	'OrGate': 'OR',
	'Inverter': 'NOT',
	'Splitter': 'SPLIT',
	'CovertGate': 'CAM',
	'TextBox': 'TEXT'
	# VCC + Switch: 'INPUT'
	# None: 'UI'
}


class ROI_Entry(NamedTuple):
	item_type: str		# AND, OR, SWITCH, UI etc.
	screen_tl_x: float 	# Top Left X-coordinate of bounding box in screen coordinates
	screen_tl_y: float 	# Top Left Y-coordinate of bounding box in screen coordinates
	width: float		# Width of bounding box in screen coordinates
	height: float		# Height of bounding box in screen coordinates
	id: int				# Id of circuit element in level file. ID elements are > 10000, buttons > 10010
	# 01: Drawing Tools
	# 02: Confirm/Switch Clicks
	# 03: Score (top right)
	# 04: Footer (Imprint etc.)
	# 10: Confirm Button


def updateCanvasSize(width: int, height: int, offset_x: int = 0, offset_y: int = 0):
	global canvas_w, canvas_h, xmax, ymax, level_scaled_w, level_scaled_h, canvas_offset

	assert width == 1280 and height == 720, "TODO There is currently calculation error with the upscaled canvas which needs to be fixed first"

	canvas_w, canvas_h = canvas_size
	canvas_offset = (offset_x, offset_y)

	xmax = canvas_w-LEVEL_MARGINS["right"]
	ymax = canvas_h-LEVEL_MARGINS["bottom"]

	level_scaled_w = xmax-xmin
	level_scaled_h = ymax-ymin


def screen_coord_to_canvas(sx: float, sy: float) -> tuple[float, float]:
	tx, ty = canvas_offset
	return (sx-tx, sy-ty)


def canvas_coord_to_screen(cx: float, cy: float) -> tuple[float, float]:
	tx, ty = canvas_offset
	return (cx+tx, cy+ty)


def canvas_coord_to_level(cx: float, cy: float) -> tuple[float, float]:    
	lx = (cx-xmin) * (level_w/level_scaled_w)
	ly = (cy-ymin) * (level_h/level_scaled_h)
	
	return (lx, ly)


def level_coord_to_canvas(lx: float, ly: float) -> tuple[float, float]:
	cx = lx * (level_scaled_w/level_w) + xmin
	cy = ly * (level_scaled_h/level_h) + ymin
	
	return (cx, cy)


def level_coord_to_screen(lx: float, ly: float) -> tuple[float, float]:
	canvas_coord = level_coord_to_canvas(lx, ly)
	return canvas_coord_to_screen(*canvas_coord)


def screen_coord_to_level(sx: float, sy: float) -> tuple[float, float]:
	canvas_coord = screen_coord_to_canvas(sx, sy)
	return canvas_coord_to_level(*canvas_coord)


def build_bounding_boxes(level: str, mergeInputs: bool = True, expand: int = 0) -> list[ROI_Entry]:
	boxes: list[ROI_Entry] = []

	with open(LEVEL_FILE_PATHS['level'] + level, encoding=gameConfig.LEVEL_ENCODING) as file:
		connections: dict[int, list[int]] = {}
		powers: dict[int, ROI_Entry] = {}
		switches: dict[int, ROI_Entry] = {}
		splitter: dict[int, ROI_Entry] = {}

		# Parse level file line by line
		for line in file:
			item = line.split('§')

			if item[0] == "connection":
				connections[int(item[1])] = list(map(int, item[2:]))

			if item[0] != "element": continue
			
			(_element, item_id, item_type, _rotation, x, y) = item[0:6]
			x, y = int(x), int(y)
			item_id = int(item_id)
			
			(size_x, size_y) = ELEMENT_SIZES[item_type]
			screen_x, screen_y = level_coord_to_screen(x, y)

			screen_bbox_w, screen_bbox_h = (size_x + 2*expand, size_y + 2*expand)
			screen_bbox_x, screen_bbox_y = (screen_x - screen_bbox_w/2, screen_y - screen_bbox_h/2)
			
			bounding_box = ROI_Entry(ELEMENT_TYPES[item_type], screen_bbox_x, screen_bbox_y, screen_bbox_w, screen_bbox_h, item_id)
			boxes.append(bounding_box)
			if item_type == 'VCC': powers[bounding_box.id] = bounding_box
			if item_type == 'Switch': switches[bounding_box.id] = bounding_box
			if item_type == 'Splitter': splitter[bounding_box.id] = bounding_box

		# Remove all splitters that are hidden ingame
		for x in splitter:
			if x in connections and len(connections[x]) == 1:
				boxes.remove(splitter[x])

		# Merge VCCs and switches into single box if enabled
		if mergeInputs:
			for p in powers:
				if p in connections and len(connections[p]) == 1:
					power = powers[p]
					switch = switches.get(connections[p][0])
					if switch == None:
						continue

					boxes.remove(power)
					boxes.remove(switch)
					box_tl = (min(power.screen_tl_x, switch.screen_tl_x), min(power.screen_tl_y, switch.screen_tl_y))
					box_br = (
						max(power.screen_tl_x + power.width, switch.screen_tl_x + switch.width), 
	       				max(power.screen_tl_y + power.height, switch.screen_tl_y + switch.height)
					)
					box_sz = (box_br[0] - box_tl[0], box_br[1] - box_tl[1])
					boxes.append(ROI_Entry("IN", box_tl[0], box_tl[1], box_sz[0], box_sz[1], id=power.id))

	return boxes


def buildUI_boxes() -> list[ROI_Entry]:
	BASE_ID = 10000
	drawtools_tl = canvas_coord_to_screen(80 - 65/2 - 2.5, 100 - 2.5) # x-offset - width/2 - border/2, y-offset - border/2
	drawtools_sz = (65 + 5, 480 + 5) # width + border, height + border
	clicks_tl = canvas_coord_to_screen(28, 22)
	clicks_sz = (169, 54)
	score_tl = canvas_coord_to_screen(998, 23)
	score_sz = (94, 19)
	footer_tl = canvas_coord_to_screen(0, 695)
	footer_sz = (395, 25)
	confirm_tl = canvas_coord_to_screen(1136, 633)
	confirm_sz = (125, 47)
	return [
		ROI_Entry("UI", drawtools_tl[0], drawtools_tl[1], drawtools_sz[0], drawtools_sz[1], id = BASE_ID + 1),
		ROI_Entry("UI", clicks_tl[0], clicks_tl[1], clicks_sz[0], clicks_sz[1], id=BASE_ID + 2),
		ROI_Entry("UI", score_tl[0], score_tl[1], score_sz[0], score_sz[1], id=BASE_ID + 3),
		ROI_Entry("UI", footer_tl[0], footer_tl[1], footer_sz[0], footer_sz[1], id=BASE_ID + 4),
		ROI_Entry("UI", confirm_tl[0], confirm_tl[1], confirm_sz[0], confirm_sz[1], id=BASE_ID + 10)
	]


def getLevelsForGroup(groupName: str, filterPhases: list[str] = []) -> list[str]:
	groupConf = gameConfig.getGroup(groupName)
	levelListFiles: list[str] = []
	levels: list[str] = []

	if len(filterPhases) < 1:
		filterPhases.extend([p for p in PHASES_WITH_LEVELS if p in groupConf])

	for phase in filterPhases:
		assert phase in groupConf, "Filter failed, the phase "  + phase + " does not exist in group " + groupName + "!"
		assert 'levels' in groupConf[phase], "Config error, key 'levels' is missing in group " + groupName + "!"

		if isinstance(groupConf[phase]['levels'], str):
			levelListFiles.append(groupConf[phase]['levels'])
		else:
			levelListFiles.extend(groupConf[phase]['levels'])

	for level_set in levelListFiles:
		# for each schedule, load all level paths
		with open("static/res/levels/" + level_set) as file:
			for line in file:
				if not line.startswith("level:"): continue
				levels.append(line[6:].strip())
		
	return levels
	

def exportROIs(groupName: str, appendUI: bool = True, expand: int = 0) -> dict[str, list[ROI_Entry]]:
	roi_list: dict[str, list[ROI_Entry]] = {}
	ui_roi = buildUI_boxes()
	
	for level in getLevelsForGroup(groupName):
		roi_list[level] = build_bounding_boxes(level, expand=expand)

		if appendUI:
			roi_list[level].extend(ui_roi)

	return roi_list


def saveCSV(rois: dict[str, list[ROI_Entry]], filePath: str = ""):
	DELIMITER = ','
	NEWLINE = '\n'
	TABLE_HEADER = ["label_name", "x_left_up", "y_left_up", "x_right_down", "y_right_down", "ID_ROI"]
	for levelName, boundingBoxes in rois.items():
		try:
			fileName = "ROI_" + levelName.strip().removesuffix('.txt').replace('/', '_') + ".csv"
			with open(os.path.join(filePath, fileName), mode='xt', encoding='UTF-8') as f:
				f.write(DELIMITER.join(TABLE_HEADER) + NEWLINE)
				for bb in boundingBoxes:
					line = [
						bb.item_type, 
						bb.screen_tl_x, bb.screen_tl_y, 
						bb.screen_tl_x + bb.width, 
						bb.screen_tl_y + bb.height,
						bb.id
					]
					f.write(DELIMITER.join(map(str, line)) + NEWLINE)
				print("Written '" + fileName + "'")
		except Exception as e:
			print(str(e))


if __name__ == "__main__":
	gameConfig.loadGameConfig()

	updateCanvasSize(width=1280, height=720, offset_x = 0, offset_y = 167)

	expand = 20 # px

	boxes_cta = exportROIs('conta', expand=expand)
	boxes_rta = exportROIs('retta', expand=expand)

	saveCSV(boxes_cta)

	boxes = {
		'CTA': boxes_cta,
		'RTA': boxes_rta
	}
