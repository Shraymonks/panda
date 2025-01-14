#!/usr/bin/env python3
import unittest
from panda import Panda
from panda.tests.safety import libpandasafety_py
import panda.tests.safety.common as common
from panda.tests.safety.common import CANPackerPanda

MSG_LENKHILFE_3 = 0x0D0  # RX from EPS, for steering angle and driver steering torque
MSG_HCA_1 = 0x0D2        # TX by OP, Heading Control Assist steering torque
MSG_MOTOR_2 = 0x288      # RX from ECU, for CC state and brake switch state
MSG_MOTOR_3 = 0x380      # RX from ECU, for driver throttle input
MSG_GRA_NEU = 0x38A      # TX by OP, ACC control buttons for cancel/resume
MSG_BREMSE_1 = 0x1A0     # RX from ABS, for ego speed
MSG_LDW_1 = 0x5BE        # TX by OP, Lane line recognition and text alerts


class TestVolkswagenPqSafety(common.PandaSafetyTest, common.DriverTorqueSteeringSafetyTest):
  cruise_engaged = False

  # Transmit of GRA_Neu is allowed on bus 0 and 2 to keep compatibility with gateway and camera integration
  TX_MSGS = [[MSG_HCA_1, 0], [MSG_GRA_NEU, 0], [MSG_GRA_NEU, 2], [MSG_LDW_1, 0]]
  STANDSTILL_THRESHOLD = 1
  RELAY_MALFUNCTION_ADDR = MSG_HCA_1
  RELAY_MALFUNCTION_BUS = 0
  FWD_BLACKLISTED_ADDRS = {2: [MSG_HCA_1, MSG_LDW_1]}
  FWD_BUS_LOOKUP = {0: 2, 2: 0}

  MAX_RATE_UP = 4
  MAX_RATE_DOWN = 10
  MAX_TORQUE = 300
  MAX_RT_DELTA = 75
  RT_INTERVAL = 250000

  DRIVER_TORQUE_ALLOWANCE = 80
  DRIVER_TORQUE_FACTOR = 3

  def setUp(self):
    self.packer = CANPackerPanda("vw_golf_mk4")
    self.safety = libpandasafety_py.libpandasafety
    self.safety.set_safety_hooks(Panda.SAFETY_VOLKSWAGEN_PQ, 0)
    self.safety.init_tests()

  def _set_prev_torque(self, t):
    self.safety.set_desired_torque_last(t)
    self.safety.set_rt_torque_last(t)

  # Ego speed (Bremse_1)
  def _speed_msg(self, speed):
    values = {"Geschwindigkeit_neu__Bremse_1_": speed}
    return self.packer.make_can_msg_panda("Bremse_1", 0, values)

  # Brake light switch (shared message Motor_2)
  def _user_brake_msg(self, brake):
    # since this signal is used for engagement status, preserve current state
    return self._motor_2_msg(brake_pressed=brake, cruise_engaged=self.safety.get_controls_allowed())

  # ACC engaged status (shared message Motor_2)
  def _pcm_status_msg(self, enable):
    self.__class__.cruise_engaged = enable
    return self._motor_2_msg(cruise_engaged=enable)

  # Driver steering input torque
  def _torque_driver_msg(self, torque):
    values = {"LH3_LM": abs(torque), "LH3_LMSign": torque < 0}
    return self.packer.make_can_msg_panda("Lenkhilfe_3", 0, values)

  # openpilot steering output torque
  def _torque_cmd_msg(self, torque, steer_req=1):
    values = {"LM_Offset": abs(torque), "LM_OffSign": torque < 0}
    return self.packer.make_can_msg_panda("HCA_1", 0, values)

  # ACC engagement and brake light switch status
  # Called indirectly for compatibility with common.py tests
  def _motor_2_msg(self, brake_pressed=False, cruise_engaged=False):
    values = {"Bremslichtschalter": brake_pressed,
              "GRA_Status": cruise_engaged}
    return self.packer.make_can_msg_panda("Motor_2", 0, values)

  # Driver throttle input (Motor_3)
  def _user_gas_msg(self, gas):
    values = {"Fahrpedal_Rohsignal": gas}
    return self.packer.make_can_msg_panda("Motor_3", 0, values)

  # Cruise control buttons (GRA_Neu)
  def _button_msg(self, _set=False, resume=False, cancel=False):
    values = {"GRA_Neu_Setzen": _set, "GRA_Recall": resume, "GRA_Abbrechen": cancel}
    return self.packer.make_can_msg_panda("GRA_Neu", 2, values)

  def test_spam_cancel_safety_check(self):
    self.safety.set_controls_allowed(0)
    self.assertTrue(self._tx(self._button_msg(cancel=True)))
    self.assertFalse(self._tx(self._button_msg(resume=True)))
    self.assertFalse(self._tx(self._button_msg(_set=True)))
    # do not block resume if we are engaged already
    self.safety.set_controls_allowed(1)
    self.assertTrue(self._tx(self._button_msg(resume=True)))

  def test_torque_measurements(self):
    # TODO: make this test work with all cars
    self._rx(self._torque_driver_msg(50))
    self._rx(self._torque_driver_msg(-50))
    self._rx(self._torque_driver_msg(0))
    self._rx(self._torque_driver_msg(0))
    self._rx(self._torque_driver_msg(0))
    self._rx(self._torque_driver_msg(0))

    self.assertEqual(-50, self.safety.get_torque_driver_min())
    self.assertEqual(50, self.safety.get_torque_driver_max())

    self._rx(self._torque_driver_msg(0))
    self.assertEqual(0, self.safety.get_torque_driver_max())
    self.assertEqual(-50, self.safety.get_torque_driver_min())

    self._rx(self._torque_driver_msg(0))
    self.assertEqual(0, self.safety.get_torque_driver_max())
    self.assertEqual(0, self.safety.get_torque_driver_min())


if __name__ == "__main__":
  unittest.main()
