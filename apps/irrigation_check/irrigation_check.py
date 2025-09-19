""" App to cross-check water flow to the irrigation system. """
from datetime import datetime
from datetime import timedelta
import typing as t

from appdaemon.plugins.hass import Hass # pyright: ignore

# pyright: reportUnknownMemberType=false

def _fmt_mins(seconds: float) -> float:
  """Convert seconds to minutes, rounded to 1 decimal place

    Args:
        seconds (int): Number of seconds
  """
  return round(seconds / 60, 1)

class IrrigationCheck(Hass):
  def initialize(self):
    """AppDaemon app initialization
    """
    # Irrigation Unlimited (auto-generated) sequence ID
    self.sequence_entity_id: str = self.args['sequence_entity_id']

    self.sprinkler_entity_id: str | None = self.args.get('sprinkler_entity_id')

    # Minimum irrigation duration to cross-check
    # Don't bother checking water usage for short watering times.
    # If it's rainy and Irrigation Controller only decides to water for 15
    # seconds then we don't really care if it worked or not. Also, 15 seconds
    # of watering might not show up in Flo's metrics.
    self.min_duration: int = self.args.get('min_duration', 3)
    # Flow rate tends to be at least 12 - 25 liters / minute.
    # Should always be >= 10 liters / minute
    self.min_expected_lpm: int = self.args.get('min_expected_lpm', 10)

    # Notification action if water flow detected (optional)
    self.notify_ok_action: str | None = self.args.get('notify_ok_action')
    # Notification action if water flow not detected (optional)
    self.notify_alert_action: str | None = self.args.get('notify_alert_action')

    # Listen for the irrigation system to be finished
    self.listen_event(self.irrigation_complete, 'irrigation_unlimited_finish')

  def irrigation_complete(self, event_type: str, data: dict[str, t.Any],
      **kwargs: dict[str, t.Any]):
    """Irrigation system finished event handler.
    Check if the irrigation system ran for a minimum amount of time, and if so
    run future events to check water usage.

    Args:
        event_type (str): Event type (fired event)
        data (dict[str, t.Any]): Event data
    """
    # Ensure that this event is for the correct irrigation system
    if data['entity_id'] == self.sequence_entity_id:
      # Schedule a check of the valve -- this might take a few seconds to close
      if (self.sprinkler_entity_id):
        # We got the event -- double-check that the valve is off
        self.run_in(self.check_valve, 10)

      # Duration in seconds
      duration = int(data['run']['duration'])
      if (duration / 60) < self.min_duration:
        self.log('Irrigation only active for %s minutes -- no check',
                 _fmt_mins(duration))
        return

      # Water usage sensors don't update immediately, and even when HA gets
      # an update it seems to have a few minutes of latency.
      self.log('Beginning irrigation checks')
      data['duration'] = duration
      # This should be taken directly from the event
      import zoneinfo
      data['finish_time'] = datetime.now(self.config['time_zone'])

      # Do the actual check in the future, which gives the water usage sensor
      # some time to update
      self.run_in(self.check_usage, 30, data)


  def check_valve(self, **kwargs: dict[str, t.Any]):
    """Check that the irrigation valve is off after irrigation event.
    """
    if (self.get_state(self.sprinkler_entity_id) == 'on'):
      self.error('Irrigation sequence %s finished event, but valve is on!',
                 self.sprinkler_entity_id)


  def check_usage(self,
      data: dict[str, t.Any], **kwargs: dict[str, t.Any]):
    """Check actual water usage against irrigation event

    Args:
        data (dict[str, t.Any]): Event data for originally fired event
    """
    # Could also check the flow rate for the time period. Flow rate and
    # total usage are both updated inconsistently, every 3 - 15 minutes.
    reported = datetime.fromisoformat(
        str(self.get_state('sensor.flo_shutoff_today_s_water_usage',
                           'last_reported')))

    finish_time = t.cast(datetime, data['finish_time'])
    latency = reported - finish_time

    # We want the reported time to be after the irrigation finished
    if reported < data['finish_time']:
      # If not, wait a bit and check again
      self.log('Water usage not yet updated (last reported %s, event at %s)',
               reported, data['finish_time'])
      self.run_in(self.check_usage, 60, data)
      return

    # If it takes more than 30 minutes then something is very wrong
    if latency > timedelta(minutes=30):
      self.error('Irrigation event too old to check (event at %s)',
                 finish_time)
      return

    # If it's more than 10 minutes but we have the data, then log a warning
    if latency > timedelta(minutes=10):
      self.log('Using a water usage report that is %s minutes after irrigation',
               _fmt_mins(latency.total_seconds()))

    # Duration in seconds
    duration = float(data['duration'])
    start_time = (datetime.now() -
                  (datetime.now(self.config['time_zone']) - finish_time) -
                  timedelta(seconds=duration))


    # History back to the start time of the irrigation event
    # It ends at the current time, which will be a bit after the most recent
    # event
    usage_liters = int(self._get_history_state_delta(
        'sensor.flo_shutoff_today_s_water_usage', start_time))

    # Assign all usage to the duration, even though that's not true
    lpm = usage_liters / (duration / 60)

    self.log('Found %s lpm over %s minutes with latency of %s minutes',
             lpm, _fmt_mins(duration), _fmt_mins(latency.total_seconds()))

    if lpm > self.min_expected_lpm:
      # Expected amount of water
      msg = (f'Found expected usage of { usage_liters } liters '
             f'over { _fmt_mins(duration) } minutes of irrigation')
      self.log(msg)

      if self.notify_ok_action:
        self.call_service(
            self.notify_ok_action.replace('.', '/'),
            service_data={'title': 'Irrigation OK',
                          'message': msg})
    else:
      # Below expected amount of water
      msg = ('Water usage did not match irrigation time - '
             f'{ _fmt_mins(duration) } minutes of irrigation but only '
             f'{ usage_liters } liters of usage')

      self.log('ALERT - %s', msg)

      if self.notify_alert_action:
        self.call_service(
            self.notify_alert_action.replace('.', '/'),
            service_data={'title': 'Irrigation Alert',
                          'message': msg})


  def _get_history_state_delta(
      self, entity_id: str, start_time: datetime) -> float:
    """Get the difference in an entity state value over time.
    Queries the entity history and calculates the difference.

    Args:
        entity_id (str): HA Entity ID
        start_time (datetime): Start time for the history query

    Returns:
        float: Difference between now and # of minutes ago
    """
    history = self.get_history(entity_id, start_time=start_time)
    assert isinstance(history, list)

    start_val = float(history[0][0]['state'])
    end_val = float(history[0][-1]['state'])

    return end_val - start_val
