import logging
from threading import Thread
import time
from typing import Any
from flask import Flask

# Prometheus Metrics
from flask.ctx import AppContext
from prometheus_flask_exporter import PrometheusMetrics, Gauge  # type: ignore
from prometheus_flask_exporter.multiprocess import UWsgiPrometheusMetrics  # type: ignore

import app.config as gameConfig
import app.storage.participantsDict as participantsDict


class ServerMetrics:
	@staticmethod
	def __prometheusFactory(auth_provider: Any):
		EXCLUDED_PATHS = ["/?res\\/.*", "/?src\\/.*", "/?doc\\/.*"]
		
		# Try to use the uWSGI exporter. This will fail, if uWSGI is not installed
		try:
			metrics = UWsgiPrometheusMetrics.for_app_factory( # type: ignore
				excluded_paths=EXCLUDED_PATHS,
				metrics_decorator=auth_provider
			)

		# Use the regular Prometheus exporter
		except Exception as e:
			logging.error(e)

			metrics = PrometheusMetrics.for_app_factory( # type: ignore
				excluded_paths=EXCLUDED_PATHS,
				metrics_decorator=auth_provider
			)

		logging.info(f'Using {type(metrics).__name__} as the Prometheus exporter')
		return metrics

	metrics: PrometheusMetrics|UWsgiPrometheusMetrics|None = None

	# ReverSim Prometheus Metrics
	#met_openLogs = Gauge("reversim_logfile_count", "The number of open logfiles") # type: ignore

	met_playersConnected: Gauge|None = None
	# NOTE Prometheus multi processing implementation prevents us from building the stats whenever requested.
	# Instead we have to use a periodic task
	#met_playersConnected.set_function(participantsDict.getConnectedPlayers)
	
	met_clientErrors: Gauge|None = None

	@classmethod
	def createPrometheus(cls, app: Flask, auth_provider: Any):
		"""Init Prometheus"""
		cls.metrics = cls.__prometheusFactory(auth_provider)
		cls.metrics.init_app(app) # type: ignore
		cls.metrics.info('app_info', 'Application info', version=gameConfig.LOGFILE_VERSION) # type: ignore
		
		cls.met_playersConnected: Gauge|None = cls.metrics.info( # type: ignore
			name='reversim_player_count',
			description="The number of players who are currently connected to the server",
			multiprocess_mode='mostrecent'
		)
		# NOTE Prometheus multi processing implementation prevents us from building the stats whenever requested.
		# Instead we have to use a periodic task
		#met_playersConnected.set_function(participantsDict.getConnectedPlayers)

		cls.met_clientErrors: Gauge|None = cls.metrics.info( # type: ignore
			name="reversim_client_errors",
			description="Number of error messages and exceptions reported by all clients",
			multiprocess_mode='sum'
		)

		with app.app_context():
			# https://github.com/rycus86/prometheus_flask_exporter/issues/31
			if isinstance(cls.metrics, UWsgiPrometheusMetrics):
				cls.metrics.register_endpoint('/metrics') # type: ignore

		# Create a periodic task that updates all metrics without an event source
		thread = Thread(target=cls.threaded_task, kwargs={'appContext': app.app_context()})
		thread.daemon = True
		thread.start()


	@classmethod
	def threaded_task(cls, appContext: AppContext):
		# Wait for 5 seconds before starting task, to give the database time to upgrade
		time.sleep(5) # [s]

		while True:
			with appContext:
				if cls.met_playersConnected is None:
					continue
				
				cls.met_playersConnected.set(participantsDict.getConnectedPlayers())

			time.sleep(gameConfig.METRIC_UPDATE_INTERVAL) # [s]


	@classmethod
	def incrementCrashMetrics(cls):
		"""Update the Prometheus metric for client errors/crashes"""
		try:
			if cls.met_clientErrors is None:
				return
			
			cls.met_clientErrors.inc() # Increment the `reversim_client_errors` metric
		except Exception as e:
			logging.error('Unable to update crash metric: ' + str(e))
