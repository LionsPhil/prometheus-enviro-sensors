## Setup display

> **Tip:** You don't *need* this to see values; see [setup-logging.md](setup-logging.md) for how to graph the measurements in either Prometheus or Grafana in a web browser.
>
> You *do* need to have set up logging first, and should heed the warning about Python 2 vs 3 there (e.g. use `pip3` and `python3` versions of packages consistently).

### Install hardware support libraries

Install the libraries for the ST7789 by following the instructions provided by Pimoroni at https://github.com/pimoroni/st7789-python.

Or, if you'd rather not install it globally, you can clone that repo and symlink `library/ST7789` module alongside this one, as for the sensors.

### Install python libraries

```shell
sudo apt install python3-requests
```

`requests` is used to pull data back out of Prometheus. You also need `pil`, but should have that via the ST7789 instructions.

### Run it!

```shell
./trend-display.py
```

If your display is in the front socket of the breakout garden instead of the back, try with `--socket front`.

If you renamed your instance, pass `--instance NAME`.

The default should rotate through the eCO2, temperature, and relative humidity readings.

Since this just runs it in your terminal, press <kbd>Ctrl</kbd>+<kbd>C</kbd> to stop it. It will automatically turn the display back off on exit.

### Configure systemd

To run it automatically, use the `prometheus-enviro-sensors-trend-display.env` and `prometheus-enviro-sensors-trend-display.service` files using the same instructions as for [configuring systemd for the logging](setup-logging.md).

You will again need to update the path (and possibly user) in the service file. Any flags you used above need to go in the environment file.

### Customize

#### Flags: fonts, metrics, and timings

`--top-font` and `--bottom-font` let you change the font in use (the size is automatic). Pass the path to a TrueType font file.

`--reverse-bottom-bar` makes the units and trend bar dark-on-light.

`--metrics` lets you list which metrics to display (e.g. `sgp30_co2_ppm`); if you only listed one, it would just show updates to that one. `--delay` sets how long, in seconds, before updating and/or moving on to the next. (The metrics need to be known; see the next section.)

Try `--help` to list some others; you can fiddle with details like the proportion of the screen used for the value, or the characters used for the trend indicators (which can be helpful if using a font that doesn't have the Unicode arrows).

For example, I run with:

```shell
./trend-display.py --socket front --top-font Antonio-Regular.ttf --trend-rising '▲' --trend-steady '━' --trend-falling '▼'
```

The font is freely licensed (SIL Open Font License) and can be [downloaded from Google Fonts](https://fonts.google.com/specimen/Antonio?query=antonio), and fits very well on the screen.

#### Source: colors, formatting, and new metrics

Look at the first 100 lines or so of the script for how to add support for displaying new metrics, or change things like colors or how many decimal places are used.

You mostly want to change the `Metric` class:

 - Its possible enum values are the flag values accepted, and must be the Prometheus metric names.
 - The `fgcolor()` and `bgcolor()`s are normal RGB hex triplets.
 - `format()` uses [Python format specifications](https://docs.python.org/3/library/string.html#formatspec) to present numbers to a sensible precision.
 - If you change which `units()` text is longest, update `METRIC_LONGEST_UNITS` too.
 - If you want to show lots of digits, update `MAX_DIGITS` so a font is measured for that many.

(Yes, this should all be configurable too, but it's more awkward to represent.)

### Other twiddles

You can do things like:

- Use `--socket custom --chip-select N --backlight M`, if you're not using the breakout garden and have the display wired into your SPI bus in some other way. (If you don't provide a backlight like this, it won't be controlled.)
- Use `--debug-display` to not use the real display at all, and instead open a stack of images on your desktop. (You may need to install `graphicsmagick-imagemagick-compat`. All the extra windows will close when you interrupt the script.)
- Point to a Prometheus instance on a different computer. You can set things up so you have one Pi capturing the sensors, having that data logged by another, and then a third running this script to query and display it.
