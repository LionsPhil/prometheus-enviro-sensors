# Prometheus Enviro Sensors

## About

This is a small python daemon (and some sample configuration) that plumbs some environment sensor modules that are suitable for use with a Raspberry Pi to the Prometheus monitoring system, which can log and graph the data.

This is absolutely a quick hack, to set expectations. But I did document it, so it's got that going for it.

### Screenshot

This is the console provided by the default configuration below:

![Screenshot of sensor graphs](console-screenshot.png)

(You can edit the Prometheus console template to your choosing, or write a different one, or even go do it via [Grafana](https://prometheus.io/docs/visualization/grafana/).)

### Supported sensors

- [SGP30](https://shop.pimoroni.com/products/sgp30-air-quality-sensor-breakout) air quality sensor (eCO/2, TVOC)
  - This one is useful over the other "air quality" sensors because it actually gives calibrated CO/2 readings, even if "equivalent", rather than an arbitrary "quality" scale.
- [BME280](https://shop.pimoroni.com/products/bme280-breakout) (temperature, pressure, humidity)

Note that it does *not* currently support all the sensors in the Pimoroni [Enviro](https://shop.pimoroni.com/products/enviro) HAT, just the BME280, although it should be easy enough to add (the name is perhaps a little aspirational). I just don't have the hardware to test (or, thus, much inclination). I would suspect that having both this and the code running the display read the sensors at the same time would work poorly, though. If you have the actual hat, it may be easier to hack *that* to export to Prometheus, than hack *this* to co-exist.

If you want to use the modules above, it's probably easier to plug them into Pimoroni's [breakout garden](https://shop.pimoroni.com/products/breakout-garden-hat-i2c-spi) (there are versions for most Pi variants now). Then everything just plugs together, which is nice.

If you have both the SGP30 and the BME280, the daemon will use the latter to provide humidity compensation data for the former; see [section 3.16 of the driver integration guide](https://www.sensirion.com/fileadmin/user_upload/customers/sensirion/Dokumente/9_Gas_Sensors/Sensirion_Gas_Sensors_SGP30_Driver-Integration-Guide_SW_I2C.pdf).

## Setup

This lists every step to get this set up on Debian (including Raspbian). If you already have a Prometheus setup, skip parts as needed.

Start by `git clone` or download/unzip -ing this repository somewhere first, of course.

### Install Prometheus

```shell
sudo apt install --no-install-recommends prometheus
```

Avoiding the recommended dependencies avoids installing a daemon set up for collecting system information, which you presumably do not care about.

### Install the Prometheus Python client library

> **Caution:** Python is kinda in a mess about the 2 to 3 migration, *still.* If getting dependencies via Debian packages, make sure you're consistent about if you install `3` versions. If using pip, make sure you're consistent about using `pip` or `pip3`. The provided systemd file below assumes you're explicitly using Python 3.

> **Note:** `pip` installs things per-user. If you're planning to run the daemon as a different user, run `pip` as that user too.

```shell
pip3 install prometheus-client
```

### Install the sensor libraries

See the Pimoroni instructions for each sensor module; they provide install scripts or `pip install` targets.

Alternatively, if you're wary of random scripts cluttering your system, it's good enough to `git clone` or download/unzip the libraries and symlink them to next to this daemon.

### Configure prometheus-enviro-sensors

Copy `prometheus-enviro-sensors.env` to `/etc/default/prometheus-enviro-sensors`. Note this removes the file extension.

Edit the ARGS variable within to have the flags you want. The defaults should be OK if you have both supported sensor types and are happy with the default monitoring port. This only applies for running it as a service, which we're about to configure---when running on the command line, pass the flags you want directly.

Create the directory used to persist the SGP30 baseline, if you're using that sensor:

```shell
sudo mkdir /var/lib/prometheus-enviro-sensors
sudo chown ${USER}:$(groups | cut -f1 -d' ') /var/lib/prometheus-enviro-sensors
```

### Configure systemd

This will start the daemon automatically as a systemd service, and let it deal with running it in the background.

Copy or symlink `prometheus-enviro-sensors.service` to `/etc/systemd/system`. Edit it to point to where you put `prometheus-enviro-sensors.py`. If you're not using the default `pi` user, change the `User=` line. You could also make a dedicated user account to run it under, if you want. It doesn't need `root` privileges.

Enable and start the service:

```shell
sudo systemctl daemon-reload
sudo systemctl enable prometheus-enviro-sensors.service
sudo systemctl start prometheus-enviro-sensors.service
sudo systemctl status prometheus-enviro-sensors.service
```

It should report `active (running)`. If you open <http://localhost:9092/> in a browser (or the IP address of the computer you're running the service on), you should get a text response of sensor values.

> **To uninstall or deactivate,** use `systemctl stop` and `systemctl disable`. The former will kill the daemon and leave the sensors/GPIO interface free to be used by other processes. The latter will remove the configuration that makes it start on boot.

### Configure Prometheus

#### Scrape config

Edit `/etc/prometheus/prometheus.yml`.

If you're just using this for the sensors, I recommend changing the `scrape_config` for `prometheus` to have a much longer `scrape_interval` and `scrape_timeout`. If you comment out Debian's defaults, and also the ones it sets under `global`, this will be the Prometheus default of one minute, which'll do. This just needlessly stores information about Prometheus' own health and performance, which you presumably don't care much about. Making this much more than a couple of minutes will mess up its own graphing, though.

You can also comment out the `node` job, unless you installed with recommended dependencies and want the system monitoring.

Add a new job for the sensors:

```yaml
- job_name: 'enviro-sensors'
  scrape_interval: 1s
  scrape_timeout: 1s
  static_configs:
    - targets: ['localhost:9092']
  relabel_configs:
    - source_labels: [__address__]
      regex: 'localhost:9092'
      target_label: instance
      replacement: 'lounge'
```

Change `lounge` to wherever your sensor is. This will give it a more useful instance name, especially if you later want to have one Prometheus server pulling in sensor data from Pi Zeros in different locations around your home or something.

Get Prometheus to reload its configuration:

```shell
sudo systemctl reload-or-restart prometheus
```

You should now be able to go to <http://localhost:9090/> (or the IP address of the computer you're setting this up on) and see the Prometheus interface. If you type `sgp30_co2_ppm` into the query box and hit `Execute` you should see a result, then click `Graph` and be able to graph it.

You can also check `Status` then `Targets` in the menu, where you should see that your `enviro-sensors` instance is `UP`.

#### Retention period

Edit `/etc/default/prometheus`, and add something like `--storage.tsdb.retention=3y` to the `ARGS` value. See the comments in that file for other options.

Note that Prometheus isn't *really* intended for long-term metrics storage. The default is 15 days. But for small data sets like this, you can probably get away with it.

Changing this will require you to *restart* Prometheus:

```shell
sudo systemctl restart prometheus
```

#### Console

On Debian, see <https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=855145>; you will want to copy and `gunzip` the `console_libraries` (and possibly `consoles`; you can symlink those).

Somewhere to your choosing in `menu.lib`:

```html
  <li {{ if eq .Path "env-sensors.html" }}class="prom_lhs_menu_selected"{{ end }}><a href="env-sensors.html?instance=lounge">Env. sensors</a></li>
```

Update `lounge` to match the instance name you used above.

(This is a bit of a hack, and doesn't bother supporting multiple sensor sets. See how the console for Prometheus itself does it; you'll need a page with a list of them. You can't use the default `_menuItem` template with a query argument because the golang 'safe' filtering will choke on it and generate a weird `#ZgotmplZ` fragID instead.)

Copy or link `env-sensors.htm` into `/etc/prometheus/consoles`.

Now you should be able to go to <http://localhost:9090/consoles/prometheus.html>, then use the navigation at the top left to look at your sensors as graphs. This is particularly handy from some *other* computer. Use the time controls at the bottom to see how air properties change throughout the day.

## TODO

There is absolutely no guarantee I'll ever get to any of this. It's an idea dumping ground. Pull requests welcome though.

- Support more of the environmental sensors, like the relevant EnviroHat ones.
  - [LTR-559](https://shop.pimoroni.com/products/ltr-559-light-proximity-sensor-breakout) (light, proximity)
  - [MICS6814](https://shop.pimoroni.com/products/mics6814-gas-sensor-breakout) (CO, NO2, NH3)
- Allow using the CPU temperature compensation logic that's in the examples for the BME280, for setups that have the board mounted directly over it. (I use a short GPIO ribbon cable.)
- For that matter, implement `vcgencmd measure_temp` as an optional sensor, so it can be compensated for Prometheus-side with a computed metric if desired.
- Bother to set up the console to support multiple instances.
- Suggest some Prometheus alerts, like high CO/2 concentrations.
- Consider doing some refactoring for sensors as a collection of instances of a subclass with register_metrics/init_sensor/measure methods, but this is a little tricksy due to the SGP30/BME280 interaction. Later, if/when there are more supported, perhaps.

Bugs/nits:

- The stderr messages *should* be going into the journal that `systemctl status` shows snippets from, but seem to be getting lost. This doesn't really matter since it's just startup messages.
- The polling isn't really every second; that's a lower-bound assuming everything else is instant, but there are known `sleep`s in the sensor libraries.
- The SGP30 baseline is not saved on graceful exit. This probably doesn't matter much since I don't think it's supposed to drift dramatically, so long as you're running the daemon for at least an hour.

Really scope-creepy stuff:

- Log to rrdtool as well, for more suitable long-term storage with downsampling.
- Show metrics or possibly Prometheus alerts on mini breakout garden displays like the [ST7789](https://shop.pimoroni.com/products/1-3-spi-colour-lcd-240x240-breakout). For example, have an alert suggest an image and a priority as labels, and if there are any, show the highest one and the metric value, else keep the screen backlight off. This should be a separate process.

## Thanks

[Posters on the Adafruit forums](https://forums.adafruit.com/viewtopic.php?f=19&t=133097#p661509), for pointing out the SGP30 really wants its baseline value saved and restored when monitoring is interrupted, otherwise it takes up to 12 hours to recover properly. The example code doesn't do this, but [the library has the methods for it](https://github.com/pimoroni/sgp30-python/blob/master/library/sgp30/__init__.py#L165). This used to be really visible as readings plummeting down to minimums on a daemon restart.

## License

Licensed under the [EUPL-1.2-or-later](https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12).
(See [GitHub's summary of its terms](https://choosealicense.com/licenses/eupl-1.2/) if unfamiliar. It's a strong copyleft open source license like the Affero GPL.)
