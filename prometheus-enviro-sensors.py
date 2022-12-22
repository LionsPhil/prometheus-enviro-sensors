#!/usr/bin/python3
# Daemon to export various Pimoroni environment sensors to Prometheus.
# Copyright 2021 Philip Boulain,
# with parts derived from MIT-licensed Pimoroni example code.
# Licensed under the EUPL-1.2-or-later.

import argparse
from datetime import datetime
import json
import math
import sys
import time

from prometheus_client import REGISTRY, start_http_server, Gauge

# Arguments
# Python doesn't seem to have a 'default true, allow --no-foo' flag, even with
# BooleanOptionalAction in 3.9 (and Raspbian is on 3.7 at time of writing).
# Prometheus export isn't optional because it's kind of what this is for (and
# will only be used if explicitly scraped).
arg_parser = argparse.ArgumentParser(description='Export environment sensors to Prometheus.')
arg_parser.add_argument('--sense-sgp30', action='store_true',
	help='Read the SGP30 air quality sensor')
arg_parser.add_argument('--sgp30-baseline-file',
	default='/var/lib/prometheus-enviro-sensors/sgp30-baseline.json',
	help='Filename for persisting the SGP30 baseline')
arg_parser.add_argument('--sgp30-humidity-compensation', action='store_true',
	help='Use the BME280 to provide the SGP30 with humidity values')
arg_parser.add_argument('--sense-bme280', action='store_true',
	help='Read the BME280 temperature/pressure/humidity sensor')
arg_parser.add_argument('--prometheus-port', type=int, default=9092,
	help='Port to export Prometheus metrics on')
arg_parser.add_argument('--prometheus-python-metrics', action='store_true',
	help='Include the default Python Prometheus metrics')
arg_parser.add_argument('--output-stdout', action='store_true',
	help='Output values to standard output')
args = arg_parser.parse_args()

if not (args.sense_sgp30 or args.sense_bme280):
	arg_parser.print_help(file=sys.stderr)
	sys.exit("\nNo sensors specified; this is probably not what you want."
		" Refusing to do nothing.")

if args.sgp30_humidity_compensation and not (args.sense_sgp30 and args.sense_bme280):
	sys.exit("Cannot perform humidity compensation without both SGP30 and BME280 sensors.")

# Metrics
if not args.prometheus_python_metrics:
	# Zap the default metrics, since we don't care at all about the health of this
	# daemon; it's not business logic to instrument. If it's up, that's good enough.
	# https://github.com/prometheus/client_python/issues/414
	for coll in list(REGISTRY._collector_to_names.keys()):
		REGISTRY.unregister(coll)

sgp30_co2 = None
sgp30_tvoc = None
if args.sense_sgp30:
	sgp30_co2 = Gauge('sgp30_co2_ppm', 'Equivalent carbon dioxide in parts per million')
	sgp30_tvoc = Gauge('sgp30_tvoc_ppb', 'Total volatile organic compounds in parts per billion')

bme280_temperature = None
bme280_pressure = None
bme280_humidity = None
if args.sense_bme280:
	bme280_temperature = Gauge('bme280_temperature_celsius', 'Ambient temperature in celsius')
	bme280_pressure = Gauge('bme280_pressure_pascals', 'Barometric pressure in pascals')
	bme280_humidity = Gauge('bme280_humidity_ratio', 'Relative humidity')

# Sensors
sgp30_sensor = None
if args.sense_sgp30:
	sys.stderr.write("Initializing SGP30\n")
	from sgp30 import SGP30

	baseline_eco2 = None
	baseline_tvoc = None
	try:
		with open(args.sgp30_baseline_file) as baseline_file:
			baseline = json.load(baseline_file)
		baseline_timestamp = float(baseline['timestamp'])
		# The one-week figure comes from the spec sheet, section 3.8:
		# https://www.sensirion.com/fileadmin/user_upload/customers/sensirion/Dokumente/9_Gas_Sensors/Sensirion_Gas_Sensors_SGP30_Driver-Integration-Guide_SW_I2C.pdf
		if baseline_timestamp < time.time() - 60*60*24*7:
			raise RuntimeError('Baseline timestamp {} is older than one week'.format(
				datetime.fromtimestamp(baseline_timestamp).isoformat()))
		baseline_eco2 = int(baseline['eco2'])
		baseline_tvoc = int(baseline['tvoc'])
	except Exception as e:
		sys.stderr.write("Bad baseline file, ignoring ({})\n".format(e))

	sgp30_sensor = SGP30()
	# It's a little ambiguous to me if this is supposed to happen regardless of
	# a baseline being saved. It's safer to do it anyway, so we do.
	# We'll simply be down from Promethus' PoV while it warms up.
	# A better approach would probably be to offer no data for this metric yet.
	sys.stderr.write("SGP30 warming up, waiting 15s\n")
	sgp30_sensor.start_measurement()

	if baseline_eco2 is not None and baseline_tvoc is not None:
		sys.stderr.write("SGP30 restoring saved baseline\n")
		sgp30_sensor.set_baseline(baseline_eco2, baseline_tvoc)

bme280_sensor = None
if args.sense_bme280:
	sys.stderr.write("Initializing SMBus and BME280\n")
	try:
		from smbus2 import SMBus
	except ImportError:
		from smbus import SMBus
	from bme280 import BME280
	smbus = SMBus(1)
	bme280_sensor = BME280(i2c_dev=smbus)
	# The first value read seems to be kinda crazy sometimes. Discard it.
	bme280_sensor.update_sensor()

# Start up the metric export.
sys.stderr.write("Starting webserver and becoming ready\n")
start_http_server(args.prometheus_port)

# Loop and poll sensors.
# The SGP30 wants to be sampled every second, so we insist on driving the
# sampling, rather than let Prometheus actually pull it. This could lead to
# some aliasing problems, and arguably the push gateway might be more correct
# here. But then that's another intermediary for what should be a very light
# system.
elapsed = 0
humidity_out_of_range_warned = False
while True:
	stdout_line = None
	if args.output_stdout:
		stdout_line = datetime.now().strftime("%H:%M:%S")

	if args.sense_sgp30:
		sgp30_result = sgp30_sensor.get_air_quality()
		sgp30_co2.set(sgp30_result.equivalent_co2)
		sgp30_tvoc.set(sgp30_result.total_voc)
		if args.output_stdout:
			stdout_line += ' eCO2: {: 5d} ppm; TVOC: {: 5d} ppb'.format(
				sgp30_result.equivalent_co2,
				sgp30_result.total_voc)

		if elapsed % 60*60 == 0:
			# This is the recommended interval for persisting the baseline.
			# It's a little dodgy to do this during the very first 12h, but
			# we can't be sure which those are. We intentionally write back the
			# baseline as soon as we start...this might also be a bit iffy.
			try:
				baseline_result = sgp30_sensor.get_baseline()
				baseline_data = {
					'timestamp': time.time(),
					'eco2': baseline_result.equivalent_co2,
					'tvoc': baseline_result.total_voc,
				}
				with open(args.sgp30_baseline_file, 'w') as baseline_file:
					json.dump(baseline_data, baseline_file)
			except Exception as e:
				sys.stderr.write("Could not persist baseline, ignoring ({})\n".format(e))

	if args.sense_bme280:
		bme280_sensor.update_sensor()
		bme280_temperature.set(bme280_sensor.temperature)
		# Pressure is given in hPa, Prometheus prefers base units; 1 hPa = 100 Pa.
		bme280_pressure.set(bme280_sensor.pressure * 100.0)
		# Humidity is given as a percentage; Prometheus prefers 0-1 scales.
		bme280_humidity.set(bme280_sensor.humidity / 100.0)
		if args.output_stdout:
			stdout_line += ' {:05.2f}°C {:05.2f}hPa {:05.2f}%'.format(
				bme280_sensor.temperature,
				bme280_sensor.pressure,
				bme280_sensor.humidity)
		if args.sgp30_humidity_compensation:
			# Work out the absolute humidity using the formula in the SGP30
			# driver integration guide, section 3.16. This seems to give values
			# that are plausible vs climate data.
			absolute_humidity = 216.7 * (
				((bme280_sensor.humidity / 100.0) * 6.112 * math.exp((17.62 * bme280_sensor.temperature) / (243.12 + bme280_sensor.temperature)))
				/ (273.15 + bme280_sensor.temperature)
			) * 1000.0
			if args.output_stdout:
				stdout_line += ' {:05.2f}mg/m³'.format(absolute_humidity)
			absolute_humidity = int(absolute_humidity)
			# If it's out of range, we turn it *off*; we don't clamp to lies.
			if absolute_humidity < 0 or absolute_humidity > 256000:
				absolute_humidity = 0
				if not humidity_out_of_range_warned:
					sys.stderr.write("Computed absolute humidity of {}mg/m³ is out of range for SGP30! Disabling compensation.\n".format(
						absolute_humidity))
					humidity_out_of_range_warned = True
			else:
				if humidity_out_of_range_warned:
					sys.stderr.write("Computed absolute humidity back in range at {}mg/m³, resuming compensation.\n".format(
						absolute_humidity))
					humidity_out_of_range_warned = False
			# There's no function for this in the Python library, but there is
			# a constant to still let us use the mid-level API.
			sgp30_sensor.command('set_humidity', [absolute_humidity])

	if args.output_stdout:
		print(stdout_line)

	time.sleep(1.0)

	# Wrap at one day to avoid long-running overflow/precision problems.
	if elapsed >= 60*60*24:
		elapsed = 0
	elapsed += 1
