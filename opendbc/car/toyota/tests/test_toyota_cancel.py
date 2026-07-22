"""Behavioral tests for the Toyota cancel path: the cancel_after_delay debounce and the
brake-clear gate that together decide when the fault-based CANCEL_REQ may be transmitted.

CANCEL_REQ forces the PCM to disengage by making it register a fault (audible chime), so
it must never be sent while the PCM is already cancelling itself due to a driver brake
press — including the up-to-~1.5s window after the pedal is released in which a hybrid
PCM can still be holding CRUISE_ACTIVE through its brake-blending logic.
"""
import unittest

from opendbc.car import structs
from opendbc.car.car_helpers import interfaces
from opendbc.car.toyota.carcontroller import BRAKE_CLEAR_MIN_FRAMES, CRUISE_CANCEL_DELAY_FRAMES

ACC_CONTROL_ADDR = 835  # 0x343; CANCEL_REQ = data[3] & 0x01 (SG_ CANCEL_REQ : 24|1@0+)
FINGERPRINT = {i: {} for i in range(7)}


def build_interface(car_name="TOYOTA_RAV4_TSS2"):
  CarInterface = interfaces[car_name]
  CP = CarInterface.get_params(car_name, FINGERPRINT, [], alpha_long=False, is_release=False, docs=False)
  CP_SP = CarInterface.get_params_sp(CP, car_name, FINGERPRINT, [], alpha_long=False, is_release_sp=False, docs=False)
  return CarInterface(CP, CP_SP)


class TestToyotaCancelPath(unittest.TestCase):
  def setUp(self):
    self.CI = build_interface()
    self.assertTrue(self.CI.CP.openpilotLongitudinalControl)
    self.CC_SP = structs.CarControlSP()
    self.now = 0
    self.CI.update([])

  def _set_brake(self, pressed: bool):
    self.CI.CS.out.brakePressed = pressed

  def _step(self, cancel: bool):
    """Run one 10ms control frame; return whether a CANCEL_REQ went out on the bus."""
    CC = structs.CarControl()
    CC.cruiseControl.cancel = cancel
    _, msgs = self.CI.apply(CC.as_reader(), self.CC_SP, self.now)
    self.now += int(0.01 * 1e9)
    return any(addr == ACC_CONTROL_ADDR and len(dat) > 3 and (dat[3] & 0x01)
               for addr, dat, _ in msgs)

  def _run(self, n: int, cancel: bool = True):
    return [self._step(cancel) for _ in range(n)]

  def test_short_cancel_transient_is_debounced(self):
    # stalk presses assert cancel for only 1-3 frames: never transmitted
    for burst in (1, 3, CRUISE_CANCEL_DELAY_FRAMES):
      self.assertFalse(any(self._run(burst)), f"{burst}-frame transient must not emit CANCEL_REQ")
      self._run(5, cancel=False)  # release; counter must reset

  def test_sustained_cancel_fires_after_delay(self):
    fired = self._run(3 * CRUISE_CANCEL_DELAY_FRAMES)
    first = fired.index(True)
    # fires once the counter exceeds the delay (ACC_CONTROL is sent at 33Hz, so allow cadence slack)
    self.assertGreaterEqual(first, CRUISE_CANCEL_DELAY_FRAMES)
    self.assertLessEqual(first, CRUISE_CANCEL_DELAY_FRAMES + 3)

  def test_counter_resets_between_episodes(self):
    self._run(2 * CRUISE_CANCEL_DELAY_FRAMES)  # first episode fires
    self._run(5, cancel=False)
    fired = self._run(CRUISE_CANCEL_DELAY_FRAMES)  # second episode must wait the full delay again
    self.assertFalse(any(fired))

  def test_brake_press_suppresses_cancel_indefinitely(self):
    self._set_brake(True)
    self.assertFalse(any(self._run(3 * BRAKE_CLEAR_MIN_FRAMES)),
                     "no CANCEL_REQ may ever be sent while the driver brakes")

  def test_brake_release_cooldown_covers_pcm_hold(self):
    # brake press, then release while the PCM could still be holding CRUISE_ACTIVE:
    # the cancel stays suppressed for BRAKE_CLEAR_MIN_FRAMES after release, then debounces
    self._set_brake(True)
    self._run(10)
    self._set_brake(False)
    self.assertFalse(any(self._run(BRAKE_CLEAR_MIN_FRAMES)),
                     "cancel must stay suppressed during the post-release cooldown")
    fired = self._run(2 * CRUISE_CANCEL_DELAY_FRAMES)
    self.assertTrue(any(fired), "after cooldown + delay a persistent cancel must still fire")


if __name__ == "__main__":
  unittest.main()
