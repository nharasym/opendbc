from opendbc.car.structs import CarParams

SteerControlType = CarParams.SteerControlType


def create_steer_command(packer, steer, steer_req):
  """Creates a CAN message for the Toyota Steer Command."""

  values = {
    "STEER_REQUEST": steer_req,
    "STEER_TORQUE_CMD": steer,
    "SET_ME_1": 1,
  }
  return packer.make_can_msg("STEERING_LKA", 0, values)


def create_lta_steer_command(packer, steer_control_type, steer_angle, steer_req, frame, torque_wind_down):
  """Creates a CAN message for the Toyota LTA Steer Command."""

  values = {
    "COUNTER": frame + 128,
    "SETME_X1": 1,  # suspected LTA feature availability
    # 1 for TSS 2.5 cars, 3 for TSS 2.0. Send based on whether we're using LTA for lateral control
    "SETME_X3": 1 if steer_control_type == SteerControlType.angle else 3,
    "PERCENTAGE": 100,
    "TORQUE_WIND_DOWN": torque_wind_down,
    "ANGLE": 0,
    "STEER_ANGLE_CMD": steer_angle,
    "STEER_REQUEST": steer_req,
    "STEER_REQUEST_2": steer_req,
    "CLEAR_HOLD_STEERING_ALERT": 0,
  }
  return packer.make_can_msg("STEERING_LTA", 0, values)


def create_lta_steer_command_2(packer, frame):
  values = {
    "COUNTER": frame + 128,
  }
  return packer.make_can_msg("STEERING_LTA_2", 0, values)


def create_accel_command(packer, accel, pcm_cancel, permit_braking, standstill_req, lead, acc_type, fcw_alert, distance):
  # TODO: find the exact canceling bit that does not create a chime
  values = {
    "ACCEL_CMD": accel,
    "ACC_TYPE": acc_type,
    "DISTANCE": distance,
    "MINI_CAR": lead,
    "PERMIT_BRAKING": permit_braking,
    "RELEASE_STANDSTILL": not standstill_req,
    "CANCEL_REQ": pcm_cancel,
    "ALLOW_LONG_PRESS": 1,
    "ACC_CUT_IN": fcw_alert,  # only shown when ACC enabled
  }
  return packer.make_can_msg("ACC_CONTROL", 0, values)


def create_accel_command_2(packer, accel):
  values = {
    "ACCEL_CMD": accel,
  }
  return packer.make_can_msg("ACC_CONTROL_2", 0, values)


def create_pcs_commands(packer, accel, active, mass):
  values1 = {
    "COUNTER": 0,
    "FORCE": round(min(accel, 0) * mass * 2),
    "STATE": 3 if active else 0,
    "BRAKE_STATUS": 0,
    "PRECOLLISION_ACTIVE": 1 if active else 0,
  }
  msg1 = packer.make_can_msg("PRE_COLLISION", 0, values1)

  values2 = {
    "DSS1GDRV": min(accel, 0),     # accel
    "PCSALM": 1 if active else 0,  # goes high same time as PRECOLLISION_ACTIVE
    "IBTRGR": 1 if active else 0,  # unknown
    "PBATRGR": 1 if active else 0, # noisy actuation bit?
    "PREFILL": 1 if active else 0, # goes on and off before DSS1GDRV
    "AVSTRGR": 1 if active else 0,
  }
  msg2 = packer.make_can_msg("PRE_COLLISION_2", 0, values2)

  return [msg1, msg2]


def create_acc_cancel_command(packer):
  values = {
    "GAS_RELEASED": 0,
    "CRUISE_ACTIVE": 0,
    "ACC_BRAKING": 0,
    "ACCEL_NET": 0,
    "CRUISE_STATE": 0,
    "CANCEL_REQ": 1,
  }
  return packer.make_can_msg("PCM_CRUISE", 0, values)


def create_fcw_command(packer, fcw):
  values = {
    "PCS_INDICATOR": 1,  # PCS turned off
    "FCW": fcw,
    "SET_ME_X20": 0x20,
    "SET_ME_X10": 0x10,
    "PCS_OFF": 1,
    "PCS_SENSITIVITY": 0,
  }
  return packer.make_can_msg("PCS_HUD", 0, values)


def create_ui_command(packer, steer, chime, left_line, right_line, left_lane_depart, right_lane_depart, enabled, stock_lkas_hud):
  values = {
    "TWO_BEEPS": chime,
    "LDA_ALERT": steer,
    "RIGHT_LINE": 3 if right_lane_depart else 1 if right_line else 2,
    "LEFT_LINE": 3 if left_lane_depart else 1 if left_line else 2,
    "BARRIERS": 1 if enabled else 0,

    # static signals
    "SET_ME_X02": 2,
    "SET_ME_X01": 1,
    "LKAS_STATUS": 1,
    "REPEATED_BEEPS": 0,
    "LANE_SWAY_FLD": 7,
    "LANE_SWAY_BUZZER": 0,
    "LANE_SWAY_WARNING": 0,
    "LDA_FRONT_CAMERA_BLOCKED": 0,
    "TAKE_CONTROL": 0,
    "LANE_SWAY_SENSITIVITY": 2,
    "LANE_SWAY_TOGGLE": 1,
    "LDA_ON_MESSAGE": 0,
    "LDA_MESSAGES": 0,
    "LDA_SA_TOGGLE": 1,
    "LDA_SENSITIVITY": 2,
    "LDA_UNAVAILABLE": 0,
    "LDA_MALFUNCTION": 0,
    "LDA_UNAVAILABLE_QUIET": 0,
    "ADJUSTING_CAMERA": 0,
    "LDW_EXIST": 1,
  }

  # lane sway functionality
  # not all cars have LKAS_HUD — update with camera values if available
  if len(stock_lkas_hud):
    values.update({s: stock_lkas_hud[s] for s in [
      "LANE_SWAY_FLD",
      "LANE_SWAY_BUZZER",
      "LANE_SWAY_WARNING",
      "LANE_SWAY_SENSITIVITY",
      "LANE_SWAY_TOGGLE",
    ]})

  return packer.make_can_msg("LKAS_HUD", 0, values)


def create_rsa_commands(speed_limit_mph: int, syncid: int):
  """RSA cluster speed-limit sign frames, byte-matched to the camera's own output
  (measured on a 2023 Highlander). Built as raw payloads so the constant fields the
  cluster expects (e.g. byte5=0x20) are reproduced exactly, not inferred from the DBC.

  speed_limit_mph: rounded mph limit to display on the cluster, or 0 to blank the sign.
  syncid: 1..15 rolling counter, advanced once per send (the cluster rejects a frozen one).
  """
  s1 = syncid & 0xF                    # RSA1 SYNCID1
  # HL-FIX(rsa-syncid): was (syncid % 15 + 1), i.e. SYNCID2 one ahead of SYNCID1, with a comment
  # claiming that matched the camera. It does not. Pairing each camera 0x489 to its nearest 0x48A
  # over route 0000000e--3dd29726fe: (SYNCID2 - SYNCID1) mod 16 == 0 for 1990/1990 frames (100.0%),
  # e.g. 0x489 ...00 0e paired with 0x48A ...08 8e. Ours ran +1 (93.4%) and never 0. The two halves
  # therefore never paired and the cluster discarded the sign. This only became visible after the
  # byte6 0x4D->0x08 fix: before that the cluster ignored us and held a stale value; after it, the
  # cluster parsed the pair, found mismatched counters, and blanked the sign entirely.
  # Revert = restore (syncid % 15 + 1) & 0xF.
  s2 = s1                              # RSA2 SYNCID2 is identical to SYNCID1 (matches camera)
  if speed_limit_mph > 0:
    # TSGN1=0x24 (mph speed sign), SPDVAL1=mph, byte5=0x20 constant; RSA2 byte6 marks the sign type.
    # HL-FIX(rsa-sign-type): byte6 was 0x4D, which is NOT the ordinary speed-limit marker. Decoded
    # from the camera's own frames on route 0000000c--69344c4094 (n=2117, 0x489 paired to 0x48A):
    #   1204x  TSGN1=0x24 b1=0x00 b6=0x08   normal speed-limit sign
    #    739x  TSGN1=0x24 b1=0x01 b6=0x08   normal speed-limit sign
    #    148x  TSGN1=0x24 b1=0xa0 b6=0x4D   a DIFFERENT sign category, 95 of whose 132 samples carry
    #                                       an implausible "5 mph" value - not a plain speed limit
    # 0x08 is 92% of the camera's output; the original capture evidently sampled one of the 148
    # special frames and generalised it. We emitted 0x4D on every frame, so the cluster never
    # rendered our value and held its last genuine camera reading (observed: dash stuck at 25 mph
    # for a whole drive while we transmitted 25/35/60/50/35/25/20).
    # Revert = restore 0x4D below.
    rsa1 = bytes([0x24, 0x00, speed_limit_mph & 0xFF, 0x00, 0x00, 0x20, 0x00, s1])
    rsa2 = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x20, 0x08, 0x80 | s2])
  else:
    # no sign: TSGN1=0 / no sign-present marker (SPDUNT=2 kept in byte7 as the camera does)
    rsa1 = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x20, 0x00, s1])
    rsa2 = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x80 | s2])
  return [(0x489, rsa1, 0), (0x48A, rsa2, 0)]


def toyota_checksum(address: int, sig, d: bytearray) -> int:
  s = len(d)
  addr = address
  while addr:
    s += addr & 0xFF
    addr >>= 8
  for i in range(len(d) - 1):
    s += d[i]
  return s & 0xFF
