#!/usr/bin/python3
# Daemon to show Prometheus enviro-sensors data on ST7789 display.
# Copyright 2021 Philip Boulain,
# with parts derived from MIT-licensed Pimoroni example code.
# Licensed under the EUPL-1.2-or-later.

import argparse
import sys
import time
from enum import Enum

import requests
from PIL import Image, ImageDraw, ImageFont

# TODO Add python3-requests and python3-pil to Debian package list in docs.

class BreakoutSocket(Enum):
    front = 'front'
    back = 'back'
    custom = 'custom'

    def __str__(self):
        return self.value

class Metric(Enum):
    """Metrics we know how to display, and how."""
    sgp30_co2_ppm = 'sgp30_co2_ppm'
    bme280_temperature_celsius = 'bme280_temperature_celsius'
    bme280_humidity_ratio = 'bme280_humidity_ratio'

    def __str__(self):
        return self.value

    @property
    def epsilon(self):
        """How far away a value can be to be trending 'level'."""
        # This doesn't compensate for non-default --lookback; assumes 10mins.
        # To some extent, this should be the inverse of normal range;
        # i.e. how much it can swing within indoor norms in 10 minutes.
        return {
            # 400~2400 => 2000 range => 100 is 5% of it
            # Drifts more dramatically in my experience
            'sgp30_co2_ppm': 100,
            # 20~25 => 5 range => 0.1 is 2% of it
            'bme280_temperature_celsius': 0.1,
            # 30~50 => 20 range => 0.4 is 2% of it
            'bme280_humidity_ratio': 0.4,
        }[self.value]

    @property
    def bgcolor(self):
        return (0x00, 0x00, 0x00)

    @property
    def fgcolor(self):
        # If you're worried about burn-in, make sure each component goes to
        # 0x00 for at least one metric which you are displaying.
        return {
            'sgp30_co2_ppm': (0x55, 0xff, 0x00),
            'bme280_temperature_celsius': (0xff, 0x55, 0x00),
            # Because blue is so dark, we boost it a bit with more green.
            'bme280_humidity_ratio': (0x00, 0xaa, 0xff),
        }[self.value]

    @property
    def units(self):
        return {
            'sgp30_co2_ppm': 'ppm',
            'bme280_temperature_celsius': '°C',
            'bme280_humidity_ratio': '%',
        }[self.value]

    def format(self, value):
        return {
            'sgp30_co2_ppm': '{:n}'.format(value),
            'bme280_temperature_celsius': '{:.1f}'.format(value),
            'bme280_humidity_ratio': '{:d}'.format(round(value * 100.0)),
        }[self.value]

arg_parser = argparse.ArgumentParser(description='Display sensor trends on ST7789.')
arg_parser.add_argument('--prometheus',
    default='http://localhost:9090',
    help='Prometheus address')
arg_parser.add_argument('--instance',
    default='lounge',
	help='Instance to show values from')
arg_parser.add_argument('--metrics', nargs='+', type=Metric,
    default=[Metric.sgp30_co2_ppm, Metric.bme280_temperature_celsius, Metric.bme280_humidity_ratio],
	help='Metrics to show')
arg_parser.add_argument('--lookback', type=float,
    default=600.0,
    help='Seconds to look back to determine trends')
arg_parser.add_argument('--max-age', type=float,
    default=60.0,
    help='Maximum tolerate age of sensor values before ignoring')
arg_parser.add_argument('--delay', type=float,
    default=3.0,
    help='Seconds to hold each metric before moving to the next')
arg_parser.add_argument('--font',
    default='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    help='Font file to for display')
arg_parser.add_argument('--trend-rising',
    default='↗',
    help='String to use for rising trend')
arg_parser.add_argument('--trend-steady',
    default='→',
    help='String to use for steady trend (sets the allocated width)')
arg_parser.add_argument('--trend-falling',
    default='↘',
    help='String to use for falling trend')
arg_parser.add_argument('--top-fraction', type=float,
    default=0.75,
    help='Vertical proportion of the display to use for the metric value')
arg_parser.add_argument('--reverse-bottom-bar', action='store_true',
    help='Draw the units and trend bar in reverse video')
arg_parser.add_argument('--socket', type=BreakoutSocket,
    choices=list(BreakoutSocket), default=BreakoutSocket.back,
    help='Breakout socket display is plugged into, or custom')
arg_parser.add_argument('--chip-select', type=int, default=0,
    help='SPI chip-select number for the display, if custom socket')
arg_parser.add_argument('--backlight', type=int, default=None,
    help='Backlight GPIO pin number for the display, if custom socket')
arg_parser.add_argument('--debug-display', action='store_true',
	help='Display locally instead of on ST7789, for development on a desktop.')
args = arg_parser.parse_args()

disp = None

if args.debug_display:
    class DummyDisplay(object):
        @property
        def width(self):
            return 240

        @property
        def height(self):
            return 240

        def display(self, image):
            sys.stderr.write(f"Dummy display {image}\n")
            image.show()
        
        def set_backlight(self, value):
            pass

    sys.stderr.write("Using a dummy display.\n")
    disp = DummyDisplay()
else:
    import ST7789

    if args.socket == BreakoutSocket.back:
        args.chip_select = ST7789.BG_SPI_CS_BACK
        args.backlight = 18
    elif args.socket == BreakoutSocket.front:
        args.chip_select = ST7789.BG_SPI_CS_FRONT
        args.backlight = 19

    sys.stderr.write(f"Initializing ST7789 at chip select {args.chip_select}, backlight {args.backlight}.\n")
    disp = ST7789.ST7789(
        port=0,
        cs=args.chip_select,
        dc=9,
        backlight=args.backlight,
        spi_speed_hz=80 * 1000 * 1000
    )

class GetMetricError(Exception):
    pass

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
    img = Image.new('RGB', (disp.width, disp.height), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)

    sys.stderr.write("Finding font sizes to use...\n")
    fonts_for_digits = {}
    # CO2 should be the highest, maxed out at 60,000 (six chars with comma).
    MAX_DIGITS = 6
    temp_font_size = 0
    height_for_value = disp.height * args.top_fraction
    height_for_bottom = (disp.height-1) - height_for_value
    for digits in range(MAX_DIGITS, 0, -1):
        (w, h) = (0, 0)
        last_font = None
        temp_font = None
        while w < disp.width and h < height_for_value:
            last_font = temp_font
            temp_font_size += 1
            temp_font = ImageFont.truetype(args.font, temp_font_size)
            # This assumes 8 is no narrower than any other digit.
            (w, h) = draw.textsize("8" * digits, temp_font)
        fonts_for_digits[digits] = last_font
        temp_font_size -= 1 # Resume from the *same* size for fewer digits.
        sys.stderr.write(f"For {digits} digits, use {temp_font_size}pt\n")
    fonts_for_digits[0] = fonts_for_digits[1] # Just in case of empty string.

    font_for_bottom = None
    while font_for_bottom == None:
        temp_font = ImageFont.truetype(args.font, temp_font_size)
        # Use 'W' as a wide character for 3x units, then space and trend.
        (w, h) = draw.textsize(f"WWW {args.trend_steady}", temp_font)
        if h <= height_for_bottom:
            font_for_bottom = temp_font
            sys.stderr.write(f"For units and trend, use {temp_font_size}pt\n")
        else:
            temp_font_size -= 1
            if temp_font_size == 0:
                raise RuntimeError("Somehow couldn't fit any bottom font size?")
    sys.stderr.write("Fonts ready, beginning display.\n")

    while True:
        for metric in args.metrics:
            value = None
            historic = None
            try:
                value = get_metric(metric, args.instance)
                historic = get_metric(metric, args.instance,
                    at_time=time.time() - args.lookback)
            except GetMetricError as err:
                sys.stderr.write(f"{err}\n")
                # TODO: This is not intended to be fatal, but is for now.
                # (Instead it should show an X or something.)
                # When unfatal-ing this, 'historic' failing should only
                # invalidate the trend, not the whole thing.
                raise

            change = value - historic
            trend_text = None
            if abs(change) < metric.epsilon:
                trend_text = args.trend_steady
            elif change > 0:
                trend_text = args.trend_rising
            else:
                trend_text = args.trend_falling

            value_text = metric.format(value)
            value_font = fonts_for_digits[min(len(value_text), MAX_DIGITS)]
            (w, h) = draw.textsize(value_text, value_font)
            value_x = (disp.width - w) / 2
            value_y = (height_for_value - h) / 2

            (w, h) = draw.textsize(metric.units, font_for_bottom)
            unit_y = ((height_for_bottom - h) / 2) + height_for_value

            (w, h) = draw.textsize(trend_text, font_for_bottom)
            trend_x = (disp.width-1) - w
            trend_y = ((height_for_bottom - h) / 2) + height_for_value

            bottom_color=None
            if args.reverse_bottom_bar:
                draw.rectangle(
                    (0, 0, disp.width, height_for_value),
                    metric.bgcolor)
                draw.rectangle(
                    (0, height_for_value, disp.width, disp.height),
                    metric.fgcolor)
                bottom_color=metric.bgcolor
            else:
                draw.rectangle((0, 0, disp.width, disp.height), metric.bgcolor)
                bottom_color=metric.fgcolor
            draw.text((value_x, value_y), value_text,
                font=value_font, fill=metric.fgcolor)
            draw.text((0, unit_y), metric.units,
                font=font_for_bottom, fill=bottom_color)
            draw.text((trend_x, trend_y), trend_text,
                font=font_for_bottom, fill=bottom_color)
            disp.display(img)
            time.sleep(args.delay)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        # Blank and turn off the display on the way out.
        # If we don't blank as well, when the Pi turns off, the backlight will
        # come back on, and show whatever was last displayed---wrong values.
        sys.stderr.write("Blanking and turning off display.\n")
        img = Image.new('RGB', (disp.width, disp.height), color=(0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, disp.width, disp.height), (0, 0, 0))
        if not args.debug_display:
            # Just a little annoying to pop up one last black rectangle.
            disp.display(img)
        disp.set_backlight(False)
        sys.exit(0)
