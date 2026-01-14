from datetime import datetime
import re
from flask import Blueprint, redirect, render_template, url_for

import app.config as gameConfig
from app.gameConfig import REVERSIM_STATIC_URL
from app.utilsGame import PhaseType

routerStatic = Blueprint('staticRoutes', __name__)

# The `static_folder` is relative to the blueprints `import_name` aka `__name__`
router_asset_path = 'None'
routerAssets = None

# Don't populate variables at import time, since the config is still unloaded
def initAssetRouter():
	"""Called by gameServer.py after the config was loaded, since the `assetRoutes` blueprint depends on it"""
	global router_asset_path, routerAssets
	router_asset_path = gameConfig.getAssetPath()
	routerAssets = Blueprint('assetRoutes', __name__, url_prefix=REVERSIM_STATIC_URL, static_url_path='/', static_folder=router_asset_path)


# Fix Markdown links in docs
@routerStatic.route('/doc/<path:filename>.md') # type: ignore
def redirect_to_doc(filename: str):
	"""Pandoc will not convert links containing .md files to .html files, therefore we need to redirect them manually"""
	return redirect(url_for('static', filename='doc/' + filename + '.html'), code=301)


# The starting page
@routerStatic.route('/index') # type: ignore
def groupIndex():
	# Show nothing if group index is disabled in config
	if not bool(gameConfig.get('groupIndex').get('enabled', True)):
		return 'Group Index disabled', 404

	# Gather all attributes which are send to the view
	groups = {}
	editorGroups = {}
	for groupName, group in gameConfig.groups().items():
		# Skip hidden groups and the internal debug groups
		if group.get('hide', False) or (groupName.startswith('debug') and groupName != 'debug'): 
			continue
		
		if PhaseType.Editor in group['phases'] or PhaseType.Viewer in group['phases']:
			selectedGroupList = editorGroups 
		else: 
			selectedGroupList = groups

		selectedGroupList[groupName] = {
			'displayName': group.get('displayName', groupName)
		}

	author = gameConfig.config('author', '')
	footer = str(gameConfig.get('groupIndex').get('footer', '')).format( 
		author=author,
		year=datetime.today().year
	)
	showDebug = bool(gameConfig.get('groupIndex').get('showDebug', True))

	# The languageDict is not available on the /index page, therefore use the footer keys as link text
	configFooter = gameConfig.getFooter()
	indexFooter = {}
	for key in configFooter:
		indexFooter[' '.join(re.findall('[a-zA-Z][^A-Z]*', key))] = configFooter[key]

	return render_template("index.html", **{
		'groups': groups,
		'editorGroups': editorGroups,
		'author': author,
		'footer': footer, # The footer that is normally shown on /index
		'ingameFooter': indexFooter, # The footer from /game and /welcome
		'showDebug': showDebug,
		'game_hash': gameConfig.getGitHash()
	})


# send back log inspector
#@routerStatic.route('/logInspector') # type: ignore
#def sendLogfileViewer():
#	"""TODO"""
#	return send_from_directory('static/', "logInspector.html")