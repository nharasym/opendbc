"""HL-FEAT(stock-hud-lat-off): what the Toyota cluster is told while openpilot is not steering.

Uses a recording packer so the assertions are on the signal VALUES, not on packed bytes --
no DBC needed and no chance of a bit-layout change masking a logic change.
"""
from opendbc.car import structs
from opendbc.car.car_helpers import interfaces
from opendbc.car.toyota import toyotacan
from opendbc.car.toyota.carcontroller import LDA_TOAST_FRAMES
from opendbc.sunnypilot.car.toyota.values import ToyotaFlagsSP


class _RecordingPacker:
  def __init__(self):
    self.values = None
    self.name = None

  def make_can_msg(self, name, bus, values):
    self.name = name
    self.values = dict(values)
    return (name, bus, values)


def _hud(enabled, flag, left_depart=False, right_depart=False, lat_enabled=None, visible=(True, True), stock_hud=None, pulse=0):
  p = _RecordingPacker()
  toyotacan.create_ui_command(p, steer=0, chime=0, left_line=visible[0], right_line=visible[1],
                              left_lane_depart=left_depart, right_lane_depart=right_depart,
                              enabled=enabled, stock_lkas_hud=stock_hud if stock_hud is not None else {},
                              stock_hud_when_lat_off=flag, lat_enabled=lat_enabled, lda_on_message=pulse)
  return p.values


# what the camera's own LKAS_HUD looks like on bus 2 (only the keys the builder reads)
_CAMERA_HUD = {"LANE_SWAY_FLD": 7, "LANE_SWAY_BUZZER": 0, "LANE_SWAY_WARNING": 0,
               "LANE_SWAY_SENSITIVITY": 2, "LANE_SWAY_TOGGLE": 1, "LDA_ON_MESSAGE": 1}


class TestStockHudWhenLatOff:
  def test_flag_off_is_upstream_even_when_not_steering(self):
    v = _hud(enabled=False, flag=False)
    assert (v["LEFT_LINE"], v["RIGHT_LINE"], v["LKAS_STATUS"], v["BARRIERS"]) == (1, 1, 1, 0)

  def test_flag_on_and_steering_is_the_cameras_centering_state(self):
    # Toyota manual: green symbol (LKAS_STATUS 2) while steering assist is centering; barriers on
    v = _hud(enabled=True, flag=True)
    assert (v["LEFT_LINE"], v["RIGHT_LINE"], v["LKAS_STATUS"], v["BARRIERS"]) == (1, 1, 2, 1)

  def test_flag_on_and_not_steering_is_the_cameras_lta_off_state(self):
    # measured by toggling the LTA button: OFF = lines 0, LKAS_STATUS 0, barriers 0
    v = _hud(enabled=False, flag=True)
    assert (v["LEFT_LINE"], v["RIGHT_LINE"], v["LKAS_STATUS"], v["BARRIERS"]) == (0, 0, 0, 0)

  def test_lkas_status_follows_lateral_only_with_the_flag(self):
    assert _hud(enabled=True, flag=True)["LKAS_STATUS"] == 2      # steering: green symbol
    assert _hud(enabled=False, flag=True)["LKAS_STATUS"] == 0     # not steering: symbol off
    assert _hud(enabled=False, flag=False)["LKAS_STATUS"] == 1    # flag off: upstream static 1
    assert _hud(enabled=True, flag=False)["LKAS_STATUS"] == 1     # flag off: never 2

  def test_lane_departure_still_draws_with_lateral_off(self):
    # openpilot's LDW keeps running with LKA off (Nick's call, 2026-10-02): orange line + orange symbol
    v = _hud(enabled=False, flag=True, left_depart=True)
    assert v["LEFT_LINE"] == 3 and v["RIGHT_LINE"] == 0 and v["LKAS_STATUS"] == 3

  def test_departure_symbol_is_orange_in_every_state(self):
    for enabled, lat_enabled in ((True, True), (False, True), (False, False)):
      assert _hud(enabled=enabled, flag=True, lat_enabled=lat_enabled, right_depart=True)["LKAS_STATUS"] == 3
    assert _hud(enabled=True, flag=False, right_depart=True)["LKAS_STATUS"] == 1   # flag off: static
    # the common real case, a departure while steering: orange line + orange symbol, bars stay
    v = _hud(enabled=True, flag=True, lat_enabled=True, right_depart=True)
    assert (v["LEFT_LINE"], v["RIGHT_LINE"], v["LKAS_STATUS"], v["BARRIERS"]) == (1, 3, 3, 1)

  def test_bars_never_show_on_an_off_cluster(self):
    # latActive can lag a door/belt event by a frame: lat_enabled False must blank the bars too
    v = _hud(enabled=True, flag=True, lat_enabled=False)
    assert (v["LEFT_LINE"], v["RIGHT_LINE"], v["LKAS_STATUS"], v["BARRIERS"]) == (0, 0, 0, 0)
    assert _hud(enabled=True, flag=False, lat_enabled=False)["BARRIERS"] == 1   # flag off: upstream

  def test_lines_follow_model_visibility_like_the_cameras_markers(self):
    # manual: solid while a marker is seen, outline otherwise -- in standby and while steering
    for enabled in (False, True):
      v = _hud(enabled=enabled, flag=True, lat_enabled=True, visible=(True, False))
      assert (v["LEFT_LINE"], v["RIGHT_LINE"]) == (1, 2)
      v = _hud(enabled=enabled, flag=True, lat_enabled=True, visible=(False, False))
      assert (v["LEFT_LINE"], v["RIGHT_LINE"]) == (2, 2)
    # LKA off: nothing drawn whatever the model sees
    v = _hud(enabled=False, flag=True, lat_enabled=False, visible=(True, True))
    assert (v["LEFT_LINE"], v["RIGHT_LINE"]) == (0, 0)

  def test_toast_pulse_goes_out_as_given_with_the_flag(self):
    assert _hud(enabled=False, flag=True, lat_enabled=True, pulse=1)["LDA_ON_MESSAGE"] == 1
    assert _hud(enabled=True, flag=True, lat_enabled=True, pulse=1)["LDA_ON_MESSAGE"] == 1
    assert _hud(enabled=False, flag=True, lat_enabled=True, pulse=0)["LDA_ON_MESSAGE"] == 0
    assert _hud(enabled=False, flag=False, pulse=1)["LDA_ON_MESSAGE"] == 0                 # flag off: upstream 0
    # the camera's own LDA_ON_MESSAGE is never mirrored (its LTA state drifts out of phase with MADS)
    assert _hud(enabled=False, flag=True, lat_enabled=True, stock_hud=_CAMERA_HUD)["LDA_ON_MESSAGE"] == 0

  def test_lane_sway_passthrough_is_untouched(self):
    v = _hud(enabled=False, flag=True, lat_enabled=True, stock_hud=dict(_CAMERA_HUD, LANE_SWAY_WARNING=2))
    assert v["LANE_SWAY_WARNING"] == 2

  def test_default_kwarg_keeps_old_call_sites_working(self):
    p = _RecordingPacker()
    toyotacan.create_ui_command(p, 0, 0, True, True, False, False, False, {})
    assert p.values["LEFT_LINE"] == 1 and p.values["LKAS_STATUS"] == 1


def _acc(stock_idle, lead=True, permit=True, standstill_req=False, cancel=False, accel=0.0):
  p = _RecordingPacker()
  toyotacan.create_accel_command(p, accel, cancel, permit, standstill_req, lead, 1, False, 0, stock_idle=stock_idle)
  assert p.name == "ACC_CONTROL"
  return p.values


class TestLkaOnButNotSteering:
  """Road test 2026-10-02: with LKA on, the symbol and lines vanished at a stop and during a turn
  signal, because CC.latActive drops there. Stock keeps them. lat_enabled carries 'switched on'."""

  def test_standstill_with_lka_on_is_the_cameras_standby_state(self):
    # parked capture: lines 2 / status 1 / bars 0 -- the 2 is "no marker seen", so model visibility off
    v = _hud(enabled=False, flag=True, lat_enabled=True, visible=(False, False))
    assert (v["LEFT_LINE"], v["RIGHT_LINE"], v["LKAS_STATUS"], v["BARRIERS"]) == (2, 2, 1, 0)
    # rolling in standby with markers seen: solid lines, white symbol, no bars
    v = _hud(enabled=False, flag=True, lat_enabled=True, visible=(True, True))
    assert (v["LEFT_LINE"], v["RIGHT_LINE"], v["LKAS_STATUS"], v["BARRIERS"]) == (1, 1, 1, 0)

  def test_turn_signal_pause_keeps_the_symbol(self):
    # blinker-pause: latActive False, mads.enabled True -> same standby state, symbol stays
    assert _hud(enabled=False, flag=True, lat_enabled=True)["LKAS_STATUS"] == 1

  def test_lka_switched_off_is_still_the_off_state(self):
    v = _hud(enabled=False, flag=True, lat_enabled=False)
    assert (v["LEFT_LINE"], v["RIGHT_LINE"], v["LKAS_STATUS"], v["BARRIERS"]) == (0, 0, 0, 0)

  def test_steering_is_the_centering_state(self):
    v = _hud(enabled=True, flag=True, lat_enabled=True)
    assert (v["LEFT_LINE"], v["RIGHT_LINE"], v["LKAS_STATUS"], v["BARRIERS"]) == (1, 1, 2, 1)

  def test_lat_enabled_none_means_same_as_enabled(self):
    # other call sites that never pass lat_enabled keep the two-state behaviour
    assert _hud(enabled=False, flag=True)["LKAS_STATUS"] == 0
    assert _hud(enabled=True, flag=True)["LKAS_STATUS"] == 2

  def test_departure_still_wins_in_standby(self):
    v = _hud(enabled=False, flag=True, lat_enabled=True, left_depart=True, visible=(False, False))
    assert v["LEFT_LINE"] == 3 and v["RIGHT_LINE"] == 2 and v["LKAS_STATUS"] == 3

  def test_flag_off_ignores_lat_enabled(self):
    v = _hud(enabled=False, flag=False, lat_enabled=True)
    assert (v["LEFT_LINE"], v["RIGHT_LINE"], v["LKAS_STATUS"], v["BARRIERS"]) == (1, 1, 1, 0)

  def test_flag_off_is_upstream_for_departure_and_outline_lines(self):
    # upstream: departure line 3, not-visible line 2, symbol static 1
    v = _hud(enabled=True, flag=False, left_depart=True)
    assert (v["LEFT_LINE"], v["RIGHT_LINE"], v["LKAS_STATUS"], v["BARRIERS"]) == (3, 1, 1, 1)
    v = _hud(enabled=False, flag=False, visible=(False, True))
    assert (v["LEFT_LINE"], v["RIGHT_LINE"], v["LKAS_STATUS"], v["BARRIERS"]) == (2, 1, 1, 0)


class TestStockIdleAccControl:
  def test_default_is_upstream(self):
    v = _acc(stock_idle=False)
    assert (v["MINI_CAR"], v["PERMIT_BRAKING"], v["RELEASE_STANDSTILL"], v["ALLOW_LONG_PRESS"]) == (True, True, True, 1)

  def test_idle_matches_stock_no_lead_tuple(self):
    # stock ADAS module's dominant idle frame: ACC_TYPE=1 ALLOW_LONG_PRESS=3, state bits 0
    v = _acc(stock_idle=True)
    assert (v["PERMIT_BRAKING"], v["RELEASE_STANDSTILL"], v["ALLOW_LONG_PRESS"], v["ACC_CUT_IN"], v["DISTANCE"]) == (0, 0, 3, 0, 0)
    assert v["ACC_TYPE"] == 1

  def test_idle_keeps_mini_car_so_low_speed_set_still_engages(self):
    # upstream's lead = leadVisible or vEgo < 12 exists so ACC can be engaged; never zero it
    assert _acc(stock_idle=True, lead=True)["MINI_CAR"] is True
    assert _acc(stock_idle=True, lead=False)["MINI_CAR"] is False

  def test_idle_never_touches_accel_or_cancel(self):
    # a non-zero accel so a regression that zeroes ACCEL_CMD cannot hide behind 0.0
    v = _acc(stock_idle=True, cancel=True, accel=1.234)
    assert v["CANCEL_REQ"] is True and v["ACCEL_CMD"] == 1.234


# ---- CarController-level: the call-site gating on the real Highlander interface ----

ACC_CONTROL_ADDR = 0x343
_FP = {i: {} for i in range(7)}


def _sig(dat, s, L):
  # DBC Motorola start bit s (MSB) -> value; same formula as the log decoder
  D = int.from_bytes(bytes(dat).ljust(8, b"\0")[:8], "big")
  p = 8 * (s // 8) + 7 - (s % 8)
  return (D >> (64 - p - L)) & ((1 << L) - 1)


def _build(flag: bool):
  name = "TOYOTA_HIGHLANDER_TSS2"
  CI = interfaces[name]
  CP = CI.get_params(name, _FP, [], alpha_long=False, is_release=False, docs=False)
  CP_SP = CI.get_params_sp(CP, name, _FP, [], alpha_long=False, is_release_sp=False, docs=False)
  if flag:
    CP_SP.flags |= ToyotaFlagsSP.STOCK_HUD_LAT_OFF.value
  ci = CI(CP, CP_SP)
  assert ci.CP.openpilotLongitudinalControl
  ci.update([])
  return ci


def _acc_bits(ci, enabled: bool, pcm_cruise: bool, frames: int = 8):
  """Drive a few 10 ms frames; return (PERMIT_BRAKING, RELEASE_STANDSTILL, ALLOW_LONG_PRESS) of the last ACC_CONTROL."""
  ci.CS.out.cruiseState.enabled = pcm_cruise
  last = None
  for i in range(frames):
    CC = structs.CarControl()
    CC.enabled = enabled
    CC.longActive = enabled
    _, msgs = ci.apply(CC.as_reader(), structs.CarControlSP(), int(i * 0.01 * 1e9))
    for addr, dat, _ in msgs:
      if addr == ACC_CONTROL_ADDR:
        last = (_sig(dat, 30, 1), _sig(dat, 31, 1), _sig(dat, 17, 2))
  assert last is not None, "ACC_CONTROL was never sent"
  return last


class TestStockIdleCallSite:
  def test_flag_off_is_upstream_when_idle(self):
    assert _acc_bits(_build(False), enabled=False, pcm_cruise=False) == (1, 1, 1)

  def test_flag_on_idle_sends_stock_bits(self):
    assert _acc_bits(_build(True), enabled=False, pcm_cruise=False) == (0, 0, 3)

  def test_flag_on_but_pcm_cruise_engaged_is_upstream(self):
    # brake-blend window / cancel frames: PCM still has cruise, openpilot does not -> upstream bits
    assert _acc_bits(_build(True), enabled=False, pcm_cruise=True) == (1, 1, 1)

  def test_flag_on_and_openpilot_engaged_is_upstream(self):
    assert _acc_bits(_build(True), enabled=True, pcm_cruise=True) == (1, 1, 1)


def _hud_sends(ci, mads_enabled: bool, gear, belt_ok=True, door_closed=True, pbrake=False, frames: int = 25,
               lat_active=False, depart=False, visible=(True, True), mads_available=True, cc_enabled=False):
  """Drive frames; return every LKAS_HUD sent as (controller frame, (LEFT_LINE, RIGHT_LINE, LKAS_STATUS, BARRIERS,
  LDA_ON_MESSAGE)). Bit positions per the DBC: LEFT 5|2, RIGHT 3|2, STATUS 7|2, BARRIERS 1|2, LDA_ON_MESSAGE 31|2."""
  ci.CS.out.gearShifter = gear
  ci.CS.out.seatbeltUnlatched = not belt_ok
  ci.CS.out.doorOpen = not door_closed
  ci.CS.out.parkingBrake = pbrake
  sends = []
  for i in range(frames):
    CC = structs.CarControl()
    CC.enabled = cc_enabled
    CC.latActive = lat_active
    CC.hudControl.leftLaneDepart = depart
    CC.hudControl.leftLaneVisible = visible[0]
    CC.hudControl.rightLaneVisible = visible[1]
    CC_SP = structs.CarControlSP()
    CC_SP.mads.available = mads_available
    CC_SP.mads.enabled = mads_enabled
    frame = ci.CC.frame
    _, msgs = ci.apply(CC.as_reader(), CC_SP, int(i * 0.01 * 1e9))
    for addr, dat, _ in msgs:
      if addr == 0x412:
        sends.append((frame, (_sig(dat, 5, 2), _sig(dat, 3, 2), _sig(dat, 7, 2), _sig(dat, 1, 2), _sig(dat, 31, 2))))
  return sends


def _hud_bits(ci, *args, **kwargs):
  """The last LKAS_HUD's bits over the driven frames (sent every 20 frames, plus on symbol/toast changes)."""
  sends = _hud_sends(ci, *args, **kwargs)
  assert sends, "LKAS_HUD was never sent"
  return sends[-1][1]


def _hud_status(ci, *args, **kwargs):
  return _hud_bits(ci, *args, **kwargs)[2]


class TestHalfWayStateInParkOrUnbuckled:
  """Road test 2026-10-02 photos: LKA button pressed in Park / unbuckled drew the symbol and road
  scene (standby bytes) although nothing could engage. Stock shows OFF there. The symbol must
  follow 'LKA on AND car drivable'."""
  GS = structs.CarState.GearShifter

  def test_park_with_lka_on_shows_off(self):
    assert _hud_status(_build(True), True, self.GS.park) == 0

  def test_reverse_and_neutral_show_off(self):
    assert _hud_status(_build(True), True, self.GS.reverse) == 0
    assert _hud_status(_build(True), True, self.GS.neutral) == 0

  def test_unbuckled_in_drive_shows_off(self):
    assert _hud_status(_build(True), True, self.GS.drive, belt_ok=False) == 0

  def test_door_open_or_park_brake_show_off(self):
    assert _hud_status(_build(True), True, self.GS.drive, door_closed=False) == 0
    assert _hud_status(_build(True), True, self.GS.drive, pbrake=True) == 0

  def test_drive_buckled_with_lka_on_shows_standby_symbol(self):
    # latActive False (not steering) but LKA on and drivable -> standby: symbol stays
    assert _hud_status(_build(True), True, self.GS.drive) == 1

  def test_lka_off_in_drive_shows_off(self):
    assert _hud_status(_build(True), False, self.GS.drive) == 0

  def test_flag_off_is_upstream_static_1_regardless(self):
    assert _hud_status(_build(False), True, self.GS.park) == 1
    assert _hud_status(_build(False), True, self.GS.drive, lat_active=True) == 1
    assert _hud_status(_build(False), True, self.GS.drive, depart=True) == 1


class TestSymbolColourThroughTheCarController:
  """The green/orange symbol states reach the wire from CC.latActive and the LDW flags."""
  GS = structs.CarState.GearShifter

  def test_steering_in_drive_is_green(self):
    assert _hud_status(_build(True), True, self.GS.drive, lat_active=True) == 2

  def test_departure_is_orange_even_with_lka_off(self):
    assert _hud_status(_build(True), True, self.GS.drive, depart=True) == 3
    assert _hud_status(_build(True), False, self.GS.drive, depart=True) == 3


class TestLinesThroughTheCarController:
  """hudControl.left/rightLaneVisible reach the wire on the right sides (the call site passes them
  positionally; a swap used to be invisible because both were always True)."""
  GS = structs.CarState.GearShifter

  def test_left_seen_only_in_standby(self):
    assert _hud_bits(_build(True), True, self.GS.drive, visible=(True, False))[:4] == (1, 2, 1, 0)

  def test_right_seen_only_while_steering(self):
    assert _hud_bits(_build(True), True, self.GS.drive, lat_active=True, visible=(False, True))[:4] == (2, 1, 2, 1)

  def test_lka_off_draws_nothing_whatever_is_seen(self):
    assert _hud_bits(_build(True), False, self.GS.drive, visible=(True, True))[:4] == (0, 0, 0, 0)

  def test_flag_off_keeps_upstream_solid_lines_whatever_the_model_sees(self):
    # controlsd's visibility feed is fork-wide; with the flag off the Toyota call site ignores it
    assert _hud_bits(_build(False), True, self.GS.drive, visible=(False, False))[:4] == (1, 1, 1, 0)
    assert _hud_bits(_build(False), True, self.GS.drive, lat_active=True, visible=(False, True))[:4] == (1, 1, 1, 1)

  def test_toast_fires_on_our_on_edge_for_6_s_and_never_on_the_off_edge(self):
    # camera behaviour (route 000000ec): pulse on 20/20 LTA-on edges, 0/19 LTA-off edges, 6.0 s long
    ci = _build(True)
    _hud_bits(ci, False, self.GS.drive, frames=5)                        # start with LKA off: no edge yet
    assert _hud_bits(ci, True, self.GS.drive, frames=25)[4] == 1         # on-edge -> toast
    assert _hud_bits(ci, True, self.GS.drive, frames=LDA_TOAST_FRAMES - 60)[4] == 1   # still on inside 6 s
    assert _hud_bits(ci, True, self.GS.drive, frames=61)[4] == 0         # ... and gone after 6 s total
    assert _hud_bits(ci, False, self.GS.drive, frames=25)[4] == 0        # off-edge: no toast

  def test_toast_is_cut_short_when_lka_goes_off_inside_6_s(self):
    ci = _build(True)
    _hud_bits(ci, False, self.GS.drive, frames=5)
    assert _hud_bits(ci, True, self.GS.drive, frames=25)[4] == 1
    assert _hud_bits(ci, False, self.GS.drive, frames=25)[4] == 0
    assert _hud_bits(ci, True, self.GS.drive, frames=25)[4] == 1         # a fresh on-edge starts a fresh toast

  def test_no_toast_at_start_when_lka_is_already_on(self):
    # the camera does not pulse at ignition (status comes up 0 or 1 with pulse 0 on ec/e2/d5)
    ci = _build(True)
    assert _hud_bits(ci, True, self.GS.drive, frames=25)[4] == 0

  def test_toast_never_pairs_with_off_bytes(self):
    # the camera never sends the toast with STATUS 0 (0 of 115 pulse frames on ec+e2); neither do we
    GS = self.GS
    ci = _build(True)
    _hud_bits(ci, False, GS.park, frames=5)
    for _, bits in _hud_sends(ci, True, GS.park, frames=30):          # button pressed in Park
      assert (bits[2], bits[4]) == (0, 0)
    ci = _build(True)
    _hud_bits(ci, False, GS.drive, frames=5)
    assert _hud_bits(ci, True, GS.drive, frames=100)[4] == 1          # on-edge in D: toast
    for _, bits in _hud_sends(ci, True, GS.drive, belt_ok=False, frames=30):   # unbuckled inside the 6 s
      assert (bits[2], bits[4]) == (0, 0)

  def test_park_press_countdown_runs_hidden_and_shows_only_if_drivable_in_time(self):
    GS = self.GS
    ci = _build(True)
    _hud_bits(ci, False, GS.park, frames=5)
    _hud_bits(ci, True, GS.park, frames=100)                           # press in Park: hidden
    assert _hud_bits(ci, True, GS.drive, frames=25)[4] == 1           # into D at 1 s: the rest shows
    ci = _build(True)
    _hud_bits(ci, False, GS.park, frames=5)
    _hud_bits(ci, True, GS.park, frames=LDA_TOAST_FRAMES + 5)          # press in Park, wait out the 6 s
    assert _hud_bits(ci, True, GS.drive, frames=25)[4] == 0           # a later Park -> Drive shift: no toast

  def test_toast_is_exactly_600_frames_on_the_wire(self):
    GS = self.GS
    ci = _build(True)
    _hud_bits(ci, False, GS.drive, frames=20)                          # on-edge lands on frame 20
    sends = _hud_sends(ci, True, GS.drive, frames=700)
    ones = [f for f, b in sends if b[4] == 1]
    zeros = [f for f, b in sends if b[4] == 0]
    assert ones[0] == 20 and ones[-1] == 600 and len(ones) == 30       # frames 20..600 every 20
    assert zeros[0] == 620                                             # 599 or 601 frames would move these

  def test_symbol_and_toast_changes_are_sent_at_once_like_the_camera(self):
    GS = self.GS
    ci = _build(True)
    _hud_bits(ci, False, GS.drive, frames=5)                           # last cadence send at frame 0
    sends = _hud_sends(ci, True, GS.drive, frames=1)                   # the on-edge is frame 5
    assert sends and sends[0][0] == 5 and sends[0][1][2] == 1 and sends[0][1][4] == 1
    sends = _hud_sends(ci, False, GS.drive, frames=1)                  # the off-edge is frame 6
    assert sends and sends[0][0] == 6 and sends[0][1][2] == 0 and sends[0][1][4] == 0
    ci = _build(False)                                                 # flag off: cadence only, like upstream
    _hud_bits(ci, False, GS.drive, frames=5)
    assert _hud_sends(ci, True, GS.drive, frames=1) == []

  def test_no_toast_from_the_openpilot_engagement_fallback(self):
    # MADS unavailable: the symbol falls back to CC.enabled, the toast must not (ACC SET is not an LKA press)
    GS = self.GS
    ci = _build(True)
    _hud_bits(ci, False, GS.drive, frames=5, mads_available=False, cc_enabled=False)
    bits = _hud_bits(ci, False, GS.drive, frames=25, mads_available=False, cc_enabled=True)
    assert bits[2] == 1 and bits[4] == 0

  def test_camera_pulse_is_not_mirrored_and_flag_off_sends_zero(self):
    ci = _build(True)
    ci.CS.lkas_hud["LDA_ON_MESSAGE"] = 1
    assert _hud_bits(ci, False, self.GS.drive, frames=25)[4] == 0
    ci = _build(False)
    _hud_bits(ci, False, self.GS.drive, frames=5)
    assert _hud_bits(ci, True, self.GS.drive, frames=25)[4] == 0        # flag off: upstream 0 even on the edge
