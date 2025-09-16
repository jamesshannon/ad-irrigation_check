This is a repository of AppDaemon apps I've made for Home Assistant.

```
irrigation_check:
  module: irrigation_check
  class: IrrigationCheck

  sequence_entity_id: binary_sensor.irrigation_unlimited_c2_s1
  notify_ok_action: notify.persistent_notification
  notify_alert_action: notify.str_notification_group

```
