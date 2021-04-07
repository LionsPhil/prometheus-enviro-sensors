# Daemon to export various Pimoroni environment sensors to Prometheus.
# Copyright 2021 Philip Boulain,
# with parts derived from MIT-licensed Pimoroni example code.
# Licensed under the EUPL-1.2-or-later.

# Basically all the stock sensible stuff like port selection, sensor selection,
# is to-do.

from sgp30 import SGP30
from prometheus_client import start_http_server, Gauge
import time
from datetime import datetime

# Metrics
sgp30_co2 = Gauge('sgp30_co2_ppm', 'Equivalent carbon dioxide in parts per million')
sgp30_tvoc = Gauge('sgp30_tvoc_ppb', 'Total volatile organic compounds in parts per billion')

# Sensors
sgp30_sensor = SGP30()
# We'll simply be down from Promethus' PoV while it warms up.
# A better approach would probably be to offer no data for this metric yet.
print("SGP30 sensor warming up, waiting 15s")
sgp30_sensor.start_measurement()

# Start up the metric export.
print("Starting webserver")
start_http_server(9092)

# Loop and poll sensors.
# The SGP30 wants to be sampled every second, so we insist on driving the
# sampling, rather than let Prometheus actually pull it. This could lead to
# some aliasing problems, and arguably the push gateway might be more correct
# here. But then that's another intermediary for what should be a very light
# system.
while True:
	sgp30_result = sgp30_sensor.get_air_quality()
	sgp30_co2.set(sgp30_result.equivalent_co2)
	sgp30_tvoc.set(sgp30_result.total_voc)
	# For debugging, print the results for now as well.
	print("{} eCO2: {: 5d} ppm; TVOC: {: 5d} (ppb)".format(datetime.now().strftime("%H:%M:%S"), sgp30_result.equivalent_co2, sgp30_result.total_voc))
	time.sleep(1.0)
