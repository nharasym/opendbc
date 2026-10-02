"""HL-FEAT(stock-hud-lat-off): what the Toyota cluster is told while openpilot is not steering.

Uses a recording packer so the assertions are on the signal VALUES, not on packed bytes --
no DBC needed and no chance of a bit-layout change masking a logic change.
"""
from opendbc.car.toyota import toyotacan


class _RecordingPacker:
  def __init__(self):
    self.values = None

  def make_can_msg(self, name, bus, values):
    assert name == "LKAS_HUD"
    self.values = dict(values)
    return (name, bus, values)


def _hud(enabled, flag, left_depart=False, right_depart=False):
  p = _RecordingPacker()
  toyotacan.create_ui_command(p, steer=0, chime=0, left_line=True, right_line=True,
                              left_lane_depart=left_depart, right_lane_depart=right_depart,
                              enabled=enabled, stock_lkas_hud={}, stock_hud_when_lat_off=flag)
  return p.values


class TestStockHudWhenLatOff:
  def test_flag_off_is_upstream_even_when_not_steering(self):
    v = _hud(enabled=False, flag=False)
    assert (v["LEFT_LINE"], v["RIGHT_LINE"], v["LKAS_STATUS"], v["BARRIERS"]) == (1, 1, 1, 0)

  def test_flag_on_and_steering_is_unchanged(self):
    v = _hud(enabled=True, flag=True)
    assert (v["LEFT_LINE"], v["RIGHT_LINE"], v["LKAS_STATUS"], v["BARRIERS"]) == (1, 1, 1, 1)

  def test_flag_on_and_not_steering_looks_like_stock_lta_off(self):
    v = _hud(enabled=False, flag=True)
    assert (v["LEFT_LINE"], v["RIGHT_LINE"], v["LKAS_STATUS"], v["BARRIERS"]) == (2, 2, 0, 0)

  def test_lane_departure_still_draws_with_lateral_off(self):
    v = _hud(enabled=False, flag=True, left_depart=True)
    assert v["LEFT_LINE"] == 3 and v["RIGHT_LINE"] == 2

  def test_default_kwarg_keeps_old_call_sites_working(self):
    p = _RecordingPacker()
    toyotacan.create_ui_command(p, 0, 0, True, True, False, False, False, {})
    assert p.values["LEFT_LINE"] == 1 and p.values["LKAS_STATUS"] == 1
