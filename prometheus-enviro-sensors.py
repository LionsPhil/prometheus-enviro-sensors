# Daemon to export various Pimoroni environment sensors to Prometheus.
# Copyright 2021 Philip Boulain,
# with parts derived from MIT-licensed Pimoroni example code.
# Licensed under the EUPL-1.2-or-later.

import sys
import time
from datetime import datetime

from sgp30 import SGP30
try:
    from smbus2 import SMBus
except ImportError:
    from smbus import SMBus
from bme280 import BME280

from prometheus_client import REGISTRY, start_http_server, Gauge

# Zap the default metrics, since we don't care at all about the health of this
# daemon; it's not business logic to instrument. If it's up, that's good enough.
# https://github.com/prometheus/client_python/issues/414
for coll in list(REGISTRY._collector_to_names.keys()):
	REGISTRY.unregister(coll)

# Metrics
sgp30_co2 = Gauge('sgp30_co2_ppm', 'Equivalent carbon dioxide in parts per million')
sgp30_tvoc = Gauge('sgp30_tvoc_ppb', 'Total volatile organic compounds in parts per billion')
bme280_temperature = Gauge('bme280_temperature_celsius', 'Ambient temperature in celsius')
bme280_pressure = Gauge('bme280_pressure_pascals', 'Barometric pressure in pascals')
bme280_humidity = Gauge('bme280_humidity_ratio', 'Relative humidity')

# Sensors
sys.stderr.write("Initializing SGP30\n")
sgp30_sensor = SGP30()
# We'll simply be down from Promethus' PoV while it warms up.
# A better approach would probably be to offer no data for this metric yet.
sys.stderr.write("SGP30 warming up, waiting 15s\n")
sgp30_sensor.start_measurement()

sys.stderr.write("Initializing SMBus and BME280\n")
smbus = SMBus(1)
bme280_sensor = BME280(i2c_dev=smbus)

# Start up the metric export.
sys.stderr.write("Starting webserver and becoming ready\n")
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

	bme280_sensor.update_sensor()
	bme280_temperature.set(bme280_sensor.temperature)
	# Pressure is given in hPa, Prometheus prefers base units; 1 hPa = 100 Pa.
	bme280_pressure.set(bme280_sensor.pressure * 100.0)
	# Humidity is given as a percentage; Prometheus prefers 0-1 scales.
	bme280_humidity.set(bme280_sensor.humidity / 100.0)

	# For debugging, print the results to stdout for now as well.
	print('{} eCO2: {: 5d} ppm; TVOC: {: 5d} ppb; {:05.2f}°C {:05.2f}hPa {:05.2f}%'.format(
		datetime.now().strftime("%H:%M:%S"),
		sgp30_result.equivalent_co2,
		sgp30_result.total_voc,
		bme280_sensor.temperature,
		bme280_sensor.pressure,
		bme280_sensor.humidity))

	time.sleep(1.0)
