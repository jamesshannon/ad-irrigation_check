""" App to cross-check water flow to the irrigation system. """
from datetime import datetime
from datetime import timedelta
import typing as t

from appdaemon.plugins.hass import Hass # pyright: ignore

# pyright: reportUnknownMemberType=false

class IrrigationCheck(Hass):
  def initialize(self):
    """AppDaemon app initialization
    """
    # Irrigation Unlimited (auto-generated) sequence ID
    self.sequence_entity_id: str = self.args['sequence_entity_id']
    # Minimum irrigation duration to cross-check
    # Don't bother checking water usage for short watering times.
    # If it's rainy and Irrigation Controller only decides to water for 15
    # seconds then we don't really care if it worked or not. Also, 15 seconds
    # of watering might not show up in Flo's metrics.
    self.min_duration: int = self.args.get('min_duration', 3)
    # Delay after irrigation finishes -- allows for updates from Moen
    self.delay_minutes: int = self.args.get('delay_minutes', 10)
    # Flow rate tends to be at least 12 - 25 liters / minute.
    # Should always be >= 10 liters / minute
    self.min_expected_lpm: int = self.args.get('min_expected_lpm', 10)
    # Notification action if water flow not detected
    self.alert_notify_action: str | None = self.args.get('alert_notify_action')

    # Listen for the irrigation system to be finished
    self.listen_event(self.irrigation_complete, 'irrigation_unlimited_finish', )

  def irrigation_complete(self, event_type: str, data: dict[str, t.Any],
      **kwargs: dict[str, t.Any]):
    """_summary_

    Args:
        event_type (str): _description_
        data (dict[str, t.Any]): _description_
    """
    if data['entity_id'] == self.sequence_entity_id:
      duration = int(int(data['run']['duration']) / 60)
      if duration < self.min_duration:
        self.log('Irrigation only active for %s mintues -- no check', duration)
        return

      # Do the actual check in the future, which gives the water usage sensor
      # some time to update
      self.log('Running irrigation check in %s minutes', self.delay_minutes)
      self.run_in(self.check_usage, self.delay_minutes * 60, data)

  def check_usage(self,
      data: dict[str, t.Any], **kwargs: dict[str, t.Any]):
    """Check actual water usage against irrigation event

    Args:
        data (dict[str, t.Any]): Event data for originally fired event
    """
    # Could also check the flow rate for the time period. Flow rate seems to be
    # updated consistently every 5 minutes; total usage is an inconsistent
    # ~10 minute frequency

    # duration of watering plus delay time
    # Technically the history shouldn't include the final 10 minutes, but it's
    # better to include it then the last 10 minutes of real usage
    duration = int(int(data['run']['duration']) / 60)
    history_mins = self.delay_minutes + duration

    usage_liters = self._get_history_state_delta(
        'sensor.flo_shutoff_today_s_water_usage', history_mins)
    usage_liters = round(usage_liters, 1)

    if usage_liters > duration * self.min_expected_lpm:
      # Expected amount of water
      self.log(('Found expected usage of %s liters '
                'over %s minutes of irrigation'),
          usage_liters, duration)
    else:
      msg = (f'Water usage did not match irrigation time - { duration } '
               f'minutes of irrigation but only { usage_liters } liters of '
               'usage')

      self.log('ALERT - %s', msg)

      if self.alert_notify_action:
        self.call_service(
            self.alert_notify_action.replace('.', '/'),
            service_data={'title': 'Irrigation Alert',
                          'message': msg})


  def _get_history_state_delta(
      self, entity_id: str, history_minutes: int) -> float:
    """Get the difference in an entity state value over time.
    Queries the entity history and calculates the difference.

    Args:
        entity_id (str): HA Entity ID
        history_minutes (int): # of minutes of history, ending now

    Returns:
        float: Difference between now and # of minutes ago
    """
    start_time = datetime.now() - timedelta(minutes=history_minutes)
    history = self.get_history(entity_id, start_time=start_time)

    # for state in history[0]:
    #   print(state['state'], state['last_changed'])
    assert isinstance(history, list)

    start_val = float(history[0][0]['state'])
    end_val = float(history[0][-1]['state'])

    return end_val - start_val
