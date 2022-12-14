#!/usr/bin/python3
# Simple one-shot output of most recent results to the CLI.
# Copyright 2022 Philip Boulain,
# with parts derived from MIT-licensed Pimoroni example code.
# Licensed under the EUPL-1.2-or-later.

# TODO: Yeah this has got some stuff to refactor with trend-display.

import argparse
import sys
import time
from enum import Enum

import requests
from PIL import Image, ImageDraw, ImageFont

class Metric(Enum):
    """Metrics we know how to display, and how."""
    sgp30_co2_ppm = 'sgp30_co2_ppm'
    bme280_temperature_celsius = 'bme280_temperature_celsius'
    bme280_humidity_ratio = 'bme280_humidity_ratio'

    def __str__(self):
        return self.value

    @property
    def name(self):
        return {
            'sgp30_co2_ppm': 'CO2',
            'bme280_temperature_celsius': 'Temperature',
            'bme280_humidity_ratio': 'Humidity',
        }[self.value]

    @property
    def units(self):
        return {
            'sgp30_co2_ppm': 'ppm', # Try smallcap ᴘᴘᴍ to avoid descenders.
            'bme280_temperature_celsius': '°C',
            'bme280_humidity_ratio': '%',
        }[self.value]

    def format(self, value):
        return {
            'sgp30_co2_ppm': '{:n}'.format(value),
            'bme280_temperature_celsius': '{:.1f}'.format(value),
            'bme280_humidity_ratio': '{:.1f}'.format(value*100.0),
        }[self.value]

arg_parser = argparse.ArgumentParser(description='Display sensor readings on CLI.')
arg_parser.add_argument('--prometheus',
    default='http://localhost:9090',
    help='Prometheus address')
arg_parser.add_argument('--instance',
    default='lounge',
	help='Instance to show values from')
arg_parser.add_argument('--metrics', nargs='+', type=Metric,
    default=[Metric.sgp30_co2_ppm, Metric.bme280_temperature_celsius, Metric.bme280_humidity_ratio],
	help='Metrics to show')
arg_parser.add_argument('--max-age', type=float,
    default=60.0,
    help='Maximum tolerate age of sensor values before ignoring')
args = arg_parser.parse_args()


class GetMetricError(Exception):
    pass

# This is deliberately identical to trend-display for later possible refactor.
def get_metric(metric, instance, job='enviro-sensors', at_time=None):
    url = args.prometheus + '/api/v1/query'
    query_args = {'query': metric, 'time': at_time}
    # It does not appear the instant-query API lets you add instance/job
    # labels to the query, so we greedily ask for everything, then filter below.
    response = None
    try:
        response = requests.get(url, query_args)
        response.raise_for_status()
    except requests.RequestException as err:
        raise GetMetricError('HTTP error querying Prometheus') from err

    # Now we've made the query, if it was for "now" (no time argument),
    # remember when we asked. This makes "too old" checking consistent for
    # both live and historic lookups.
    # (If you were wondering why the parameter was at_time, here it is.
    # Ugh. Horrible shadowing/namespacing problems.)
    if at_time == None:
        at_time = time.time()

    data = None
    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError as err:
        raise GetMetricError('Got bad JSON from Prometheus') from err
    try:
        if data['status'] != 'success':
            raise GetMetricError('Non-success response from Prometheus')
        for result in data['data']['result']:
            rm = result['metric']
            if rm['instance'] == instance and rm['job'] == job:
                age = at_time - result['value'][0]
                if age <= args.max_age:
                    v = result['value'][1]
                    try:
                        return float(v)
                    except ValueError as err:
                        raise GetMetricError(f"Bad metric value '{v}' from Prometheus") from err
                else:
                    raise GetMetricError(f"Data from Prometheus for '{metric}' instance=\"{instance}\", job=\"{job}\" is too old ({age} > {args.max_age} seconds)")
        # Didn't find it in results
        raise GetMetricError(f"No data from Prometheus for {metric} instance=\"{instance}\", job=\"{job}\"")
    except KeyError as err:
        # This means the structure wasn't what we expected according to
        # https://prometheus.io/docs/prometheus/latest/querying/api/#instant-queries
        raise GetMetricError('Got unexpected JSON from Prometheus') from err

def main():
    output=[]
    for metric in args.metrics:
        value = None
        try:
            value = get_metric(metric, args.instance)
        except GetMetricError as err:
            sys.stderr.write(f"{err}\n")

        value_text = '[ERROR]'

        if value != None:
            value_text = metric.format(value)

        output.append(f"{metric.name}: {value_text}{metric.units}")

    print("  ".join(output))

if __name__ == '__main__':
    main()
    sys.exit(0)
