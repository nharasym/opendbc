"""HL-FIX(lda-button-edges): the LDA/LKAS button as carstate sees it on the 2023 Highlander.

Every physical press toggles the camera's own LKAS_STATUS 0 <-> nonzero on LKAS_HUD (bus 2); the
LDA_ON_MESSAGE pulse rises only on the camera's on-edge. The camera also goes 1 -> 2 by itself and
self-cancels 2 -> 0 without a press. This pins the carstate rule; the panda applies the same one.
"""
from opendbc.car import structs
from opendbc.car.toyota.carstate import LKAS_STATUS_ACTIVE
from opendbc.car.toyota.values import DBC, CAR
from opendbc.can import CANPacker
from opendbc.car.car_helpers import interfaces

ButtonType = structs.CarState.ButtonEvent.Type


class _Harness:
  """Feeds LKAS_HUD frames through a real CarInterface and counts the lkas button presses it emits."""

  def __init__(self):
    name = "TOYOTA_HIGHLANDER_TSS2"
    CI = interfaces[name]
    fp = {i: {} for i in range(7)}
    CP = CI.get_params(name, fp, [], alpha_long=False, is_release=False, docs=False)
    CP_SP = CI.get_params_sp(CP, name, fp, [], alpha_long=False, is_release_sp=False, docs=False)
    self.ci = CI(CP, CP_SP)
    self.packer = CANPacker(DBC[CAR.TOYOTA_HIGHLANDER_TSS2]["pt"])
    self.t = 0

  def hud(self, status, pulse, dt_s=1.0):
    """One camera state, held for two frames: the CAN parser reports a message's values only from
    its second frame (the first one just seeds its timing), and the real bus repeats every frame."""
    presses = 0
    for _ in range(2):
      self.t += int(dt_s * 1e9 / 2)
      addr, dat, bus = self.packer.make_can_msg("LKAS_HUD", 2, {"LKAS_STATUS": status, "LDA_ON_MESSAGE": pulse})
      cs, _ = self.ci.update([[self.t, [(addr, dat, bus)]]])
      presses += sum(1 for e in cs.buttonEvents if e.type == ButtonType.lkas and e.pressed)
    return presses


class TestLkasButtonEdges:
  def test_first_sample_is_a_baseline(self):
    h = _Harness()
    assert h.hud(1, 0) == 0            # camera remembers LTA on at boot: not a press
    assert h.hud(0, 0) == 1            # the driver presses it off: a press

  def test_on_and_off_edges_count_once_each_regardless_of_timing(self):
    h = _Harness()
    h.hud(0, 0)
    assert h.hud(1, 1) == 1            # on-press
    assert h.hud(1, 1) == 0            # repeat: no edge
    assert h.hud(1, 0, dt_s=6.0) == 0  # the pulse times out: not a press
    assert h.hud(0, 0, dt_s=20.0) == 1 # off-press 26 s later, no pulse: still a press (the old double-press hole)

  def test_camera_self_cancel_is_not_a_press(self):
    h = _Harness()
    h.hud(0, 0)
    assert h.hud(1, 1) == 1
    assert h.hud(LKAS_STATUS_ACTIVE, 1, dt_s=2.6) == 0   # camera goes active by itself
    assert h.hud(0, 0, dt_s=2.0) == 0                     # ... and cancels itself: not a press
    assert h.hud(1, 1) == 1                               # the next real press counts

  def test_boot_ready_without_pulse_is_not_a_press(self):
    h = _Harness()
    h.hud(0, 0)
    assert h.hud(1, 0) == 0            # 0 -> 1 with no pulse: the camera becoming ready
    assert h.hud(0, 0) == 1            # then a real off-press
