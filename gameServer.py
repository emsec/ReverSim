import logging
import mimetypes
import os

# Import the Flask webserver
from flask import Flask
from markupsafe import escape
from werkzeug import Response

# import the other modules, belonging to this app
import app.config as gameConfig
from app.model.LevelLoader.JsonLevelList import JsonLevelList
import app.router.routerGame as routerGame

# import all routes, belonging to this app
import app.router.routerStatic as routerStatic
from app.model.GroupStats import GroupStats
from app.prometheusMetrics import ServerMetrics
from app.storage.ParticipantLogger import ParticipantLogger
from app.storage.crashReport import openCrashReporterFile
from app.storage.database import ReverSimDatabase
from app.storage.modelFormatError import ModelFormatError
from app.storage.participantScreenshots import ScreenshotWriter
from app.utilsGame import safe_join

# Fix mime type on Windows https://github.com/pallets/flask/issues/1045
mimetypes.add_type('text/css', '.css')
mimetypes.add_type('text/html', '.html')
mimetypes.add_type('text/javascript', '.js')
mimetypes.add_type('image/png', '.png')
mimetypes.add_type('image/svg+xml', '.svg')
mimetypes.add_type('application/json', '.json')


class DefaultFlaskSettings:
	"""The default settings that are applied if not overridden by a file.

	You can specify the path to the Flask config with the `FLASK_CONFIG` 
	environment variable.
	"""
	# Limit the upload file size
	MAX_CONTENT_LENGTH = 2 * 1024 * 1024 # 2MB max content length
	MAX_FORM_MEMORY_SIZE = MAX_CONTENT_LENGTH
	SQLALCHEMY_DATABASE_URI = "sqlite+pysqlite:///statistics/reversim.db" # instance/statistics/reversim.db
	SQLALCHEMY_ECHO = False
	SQLALCHEMY_ENGINE_OPTIONS = {
		"connect_args": {
			# time in seconds after which Database Is Locked will be thrown
			"timeout": 10 # TODO Choose short in production to recover faster from deadlocks
		}
	}


def createCrashReporter(app: Flask):
	# If crash reporter is enabled, open file to write client errors into
	if gameConfig.getInt('crashReportLevel') > 0:
		crashReporterFilePath: str = safe_join(
			app.instance_path,
			app.config.get('CLIENT_ERROR_LOG', 'statistics/crash_reporter.log') # type: ignore
		)

		openCrashReporterFile(
			crashReporterFilePath,
			gameConfig.getGroupsDisabledErrorLogging(),
			ServerMetrics.met_clientErrors, # type: ignore
			errorLevel=gameConfig.getInt('crashReportLevel')
		)


def initLegacyLogFile(app: Flask):
	"""Init the Legacy Logfile writer, create the necessary folder structure"""

	ParticipantLogger.baseFolder = os.path.join(
		app.instance_path, "statistics/LogFiles"
	)

	try:
		os.makedirs(ParticipantLogger.baseFolder, exist_ok=True)
	except Exception:
		logging.exception(f'Unable to create folder "{ParticipantLogger.baseFolder}"')


def initScreenshotWriter(app: Flask):
	"""Init the Screenshot writer, create the necessary folder structure"""

	ScreenshotWriter.screenshotFolder = os.path.join(
		app.instance_path, "statistics/canvasPics"
	)

	try:
		os.makedirs(ScreenshotWriter.screenshotFolder, exist_ok=True)
	except Exception:
		logging.exception(f'Unable to create folder "{ScreenshotWriter.screenshotFolder}"')


def createMinimalApp():
	""""""
	instancePath = os.environ.get("REVERSIM_INSTANCE", "./instance")

	# Start the webserver
	app = Flask(__name__, 
		static_url_path='', 
		static_folder='./static', 
		template_folder='./templates',
		instance_path=os.path.abspath(instancePath),
		instance_relative_config=True
	)

	# Load config object and then override with config file if it exists
	# NOTE config.from_object does not accept a Dict, only a class!
	app.config.from_object(DefaultFlaskSettings)
	#app.config.from_envvar('FLASK_CONFIG', silent=True) # TODO Allow overriding Flask config

	# Load game config
	REVERSIM_CONF = os.environ.get("REVERSIM_CONFIG", "conf/gameConfig.json")
	gameConfig.loadGameConfig(REVERSIM_CONF, app.instance_path)
	JsonLevelList.singleton = JsonLevelList.fromFile(instanceFolder=app.instance_path)

	return app


# Create the webserver
def createApp():
	"""Flask app factory pattern"""

	logging.basicConfig(
		level=logging.INFO,
	)

	app = createMinimalApp()

	# Init Flask Routes
	routerStatic.initAssetRouter()
	app.register_blueprint(routerStatic.routerStatic)
	app.register_blueprint(routerGame.routerGame)
	app.register_blueprint(routerStatic.routerAssets)

	logging.info(f'Instance path: {app.instance_path}')

	# Init the Database
	ReverSimDatabase.createDatabase(app)

	# Init the Legacy logger and Screenshots
	initScreenshotWriter(app)
	initLegacyLogFile(app)

	# Init Prometheus (must be done before Flask context is created)
	ServerMetrics.createPrometheus(app)

	return app


flaskInstance = createApp()


@flaskInstance.before_request
def post_flask_init():
	"""Called after the flask application context was created
	
	Have to resort to a `app.before_request` hook that gets deleted, since the Flask team
	decided to remove the only method that allowed a post init hook to be implemented.
	https://stackoverflow.com/a/77949082

	And no just using `with app.app_context():` inside of `createApp()` is not feasible,
	as some things must not be loaded when using e.g. the `flask db` cli.
	"""
	logging.info("Running post-init")
	flaskInstance.before_request_funcs[None].remove(post_flask_init)

	# GroupStats depends on database, so upgrades must be done by now
	with flaskInstance.app_context():
		GroupStats.createGroupCounters()
	
	# Init Crash reporter (depends on Prometheus)
	createCrashReporter(flaskInstance)


# set response headers
@flaskInstance.after_request # type: ignore
def apply_caching(response: Response) -> Response:
	"""Apply response caching headers to every request to protect against XSS attacks"""
	# Prevents external sites from embedding your site in an iframe
	#response.headers["X-Frame-Options"] = "SAMEORIGIN"

	# Tells the browser to convert all HTTP requests to HTTPS, preventing man-in-the-middle (MITM) attacks.
	#response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
	
	# Tell the browser where it can load various types of resource from
	#response.headers['Content-Security-Policy'] = "default-src 'self'"

	# Forces the browser to honor the response content type instead of trying to detect it, 
	# which can be abused to generate a cross-site scripting (XSS) attack.
	#response.headers['X-Content-Type-Options'] = 'nosniff'

	# The browser will try to prevent reflected XSS attacks by not loading the page if the request 
	# contains something that looks like JavaScript and the response contains the same data.
	response.headers['X-XSS-Protection'] = '1; mode=block'
	return response


@flaskInstance.errorhandler(ModelFormatError)
def handle_model_format_errors(e: Exception):
	"""Throw a meaningful error if something is wrong in the gameConfig.json, or if the
	player is trying to access an unknown group"""
	# NOTE: The escape method is necessary to prevent injection attacks!
	return escape(e), 500


# If the script is run from the command line, start the local flask debug server
if __name__ == "__main__":
	flaskInstance.run()
