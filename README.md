# Prometheus Enviro Sensors

blah blah link to the pimoroni stuff here

Supported sensors:
 - SGP30
 - BME280

## Example Prometheus scrape config

```yaml
- job_name: 'enviro-sensors'
  scrape_interval: 1s
  scrape_timeout: 1s
  static_configs:
    - targets: ['localhost:9092']
```
