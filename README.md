

```
# Irrigation Check AppDaemon App

## Purpose
This AppDaemon app helps prevent irrigation failures by cross-checking the logical Home Assistant irrigation controller (e.g., Irrigation Unlimited) with the physical valve and water flow. It ensures that:

1. The irrigation valve is actually closed after the controller finishes.
2. The expected amount of water was used, as measured by a water meter.

This helps detect under-watering (valve didn't open) or over-watering (valve stuck open), both of which can be serious for plant health and water usage.

## Installation
1. Copy `irrigation_check.py` to your AppDaemon apps directory (or symlink for development).
2. Add the configuration below to your AppDaemon `apps.yaml`.
3. Reload AppDaemon or restart the app.

## Configuration
Add an entry to your `apps.yaml`:

```yaml
irrigation_check:
  module: irrigation_check
  class: IrrigationCheck

  sequence_entity_id: binary_sensor.irrigation_unlimited_c2_s1  # The logical controller's sequence entity
  sprinkler_entity_id: switch.sprinkler_controller_zone_3_relay # (Optional) The physical valve entity

  notify_ok_action: notify.persistent_notification              # (Optional) Service to notify if check passes
  notify_alert_action: notify.str_notification_group            # (Optional) Service to notify if check fails

  min_duration: 3         # (Optional) Minimum watering duration (minutes) to check (default: 3)
  min_expected_lpm: 10    # (Optional) Minimum expected flow rate (liters/min, default: 10)
```

### Required Arguments
- `sequence_entity_id`: The entity_id of the irrigation controller sequence (e.g., from Irrigation Unlimited)

### Optional Arguments
- `sprinkler_entity_id`: The entity_id of the physical valve (switch)
- `notify_ok_action`: Home Assistant notify service to call if water usage is as expected
- `notify_alert_action`: Home Assistant notify service to call if water usage is below expected
- `min_duration`: Minimum watering duration (in minutes) to check
- `min_expected_lpm`: Minimum expected liters per minute

## How It Works
When the irrigation controller finishes a run, the app:
1. Optionally checks that the valve is off.
2. Waits for a configurable delay to allow water meter updates.
3. Checks the water usage during the run. If usage is below expected, sends an alert; otherwise, sends an OK notification.

## Example Use Case
If a zone is scheduled to run for 10 minutes, but the water meter shows only 5 liters used (instead of the expected 100+), the app will alert you to a possible valve or plumbing issue.

## Troubleshooting
- Ensure your water meter entity is updating correctly in Home Assistant.
- Adjust `min_duration`, `delay_minutes`, and `min_expected_lpm` as needed for your system.

## License
MIT
