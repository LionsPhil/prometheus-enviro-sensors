# Prometheus Enviro Sensors

blah blah link to the pimoroni stuff here

Supported sensors:

- SGP30
- BME280

## Example Prometheus config fragments

### Scrape config

In `/etc/prometheus/prometheus.yml`:

```yaml
- job_name: 'enviro-sensors'
  scrape_interval: 1s
  scrape_timeout: 1s
  static_configs:
    - targets: ['localhost:9092']
```

### Console

On Debian, see <https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=855145>; you will want to copy and `gunzip` the `console_libraries` (and possibly `consoles`; you can symlink those).

Somewhere to your choosing in `menu.lib`:

```html
  <li {{ if eq .Path "env-sensors.html" }}class="prom_lhs_menu_selected"{{ end }}><a href="env-sensors.html?instance=localhost:9092">Env. sensors</a></li>
```

(This is a bit of a hack, and doesn't bother supporting multiple sensor sets. See how the console for Prometheus itself does it; you'll need a page with a list of them. You can't use the default `_menuItem` template with a query argument because the golang 'safe' filtering will choke on it and generate a weird `#ZgotmplZ` fragID instead.)

Copy or link `env-sensors.htm` into `/etc/prometheus/consoles`.
