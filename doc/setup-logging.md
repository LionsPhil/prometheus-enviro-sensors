## Setup logging

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

#### Moving the database

Prometheus [stores data](https://prometheus.io/docs/prometheus/latest/storage/) via a write-ahead log, and you can't turn this off, because it's designed to not lose metrics for monitoring something important.

Since this implies making a bunch of writes, you might want to move it off the SD card your Raspbian install is on. I don't have data for if this is a real concern, and SD cards do apparently have hardware wear levelling, so it's probably fine.

Still, if you want to move the database to a USB stick, for example one of the tiny ones that fits almost entirely within the socket:

- Use `lsblk` to find the right device for the USB stick. Set a variable: \
  `DEVICE=/dev/sdz1`
- Format it as a Linux filesystem; don't use FAT: \
  `sudo mkfs.ext4 -v -L 'prometheuslogs' ${DEVICE:?}`.
- Mount it to a temporary directory: \
  `mkdir /tmp/plogs && sudo mount ${DEVICE:?} /tmp/plogs`
- Stop Prometheus: \
  `sudo systemctl stop prometheus.service`
- Move the data:
  `sudo mv -iv /var/lib/prometheus/metrics2 /tmp/plogs/`
- Add a line to `/etc/fstab` to mount the device over the Prometheus data directory: \
  `LABEL=prometheuslogs /var/lib/prometheus  ext4  errors=remount-ro,nodev,barrier=1,journal_checksum,nofail  0  0`
- Unmount the temporary directory, and remount in its new home: \
  `sudo umount /tmp/plogs && rmdir /tmp/plogs && sudo mount /var/lib/prometheus`
- Check the `metrics2` directory is still there: \
  `ll /var/lib/prometheus`
- Start Prometheus back up: \
  `sudo systemctl start prometheus.service`

Careful: if you start your Pi without the USB stick attached, it will boot, but Prometheus might start logging a new, separate history on the SD card again, since it's your root filesystem. (I'm not sure if it will recreate the `metrics2` directory.)

If you'd rather have the USB key mounted elsewhere, you could also set `--storage.tsdb.path` under `/etc/default/prometheus` to point to a path under it instead.

### Configure Grafana

Optional, but has a nicer dashboard, that displays in local timezone and works better on mobile.

Grafana have [instructions for installing on Raspbian](https://grafana.com/tutorials/install-grafana-on-raspberry-pi/). Follow the "Install Granafa" section to set up the APT respository, but *don't* start the server yet.

For a personal install, you probably want to edit `/etc/grafana/grafana.ini` and change some things:

- Under `[analytics]`&hellip;
  - &hellip;set `reporting_enabled` to `false`. (Don't phone home that it's running.)
  - &hellip;set `check_for_updates` to `false`. (APT will do this for you.)
- Under `[security]`, set `disable_gravatar` to `true`. (This will stop it making external web requests for profile pictures you're not using.)
- Under `[alerting]`, set `enabled` to `false`. (This is Prometheus' job, if you want it.)

Then you can resume the setup instructions with starting the server and logging in. Check the Grafana documentation for how to build a dashboard. (It's less amicable to shipping a stock one since it wraps all its config in a SQLite database.) See the screenshot above for inspiration.

The metrics you want to plot will be named like the Prometheus queries for its console, e.g. `sgp30_co2_ppm{job='enviro-sensors',instance='lounge'}`. You can set units for them under "Field", and set up some thresholds (these aren't alerts, just lines). Change the color before clicking the legend (then consider turning the legend off).