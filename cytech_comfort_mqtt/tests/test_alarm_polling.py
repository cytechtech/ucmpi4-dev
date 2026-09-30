import ast
import logging
import re
import unittest
from pathlib import Path
from queue import Queue, Empty
from types import SimpleNamespace
from unittest.mock import Mock

BASE = Path(__file__).resolve().parents[1] / 'rootfs' / 'comfort2'

class AlarmPollingTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((BASE / 'bridge.py').read_text(encoding='utf-8-sig'))
        methods = [n for c in tree.body if isinstance(c, ast.ClassDef) for n in c.body
                   if isinstance(n, ast.FunctionDef) and n.name in ('process_serial_queue', 'handle_serial_line', 'login')]
        self.clock = Mock(return_value=1000.0)
        self.settings = SimpleNamespace(COMFORTCONNECTED=True, PASSTHROUGH_ACTIVE=False,
                                        BROKERCONNECTED=False, FIRST_LOGIN=False,
                                        ALARMCONNECTEDTOPIC='connected', REFRESHTOPIC='refresh')
        self.env = dict(time=SimpleNamespace(monotonic=self.clock, sleep=Mock()),
                        settings=self.settings, Empty=Empty, logger=logging.getLogger('poll-test'),
                        comfort_protocol=SimpleNamespace(ComfortLUUserLoggedIn=lambda _: SimpleNamespace(user=1)))
        exec(compile(ast.Module(body=methods, type_ignores=[]), 'bridge.py', 'exec'), self.env)
        self.bridge = SimpleNamespace(serial=SimpleNamespace(is_open=True, write=Mock()),
             alarm_status=Mock(), _alarm_last_report=1000.0, _alarm_snapshot_due=0.0,
             serial_queue=Queue(), _line_pattern=re.compile(r'(\x03[^\r]+)'),
             handle_serial_line=Mock(), publish=Mock(), setdatetime=Mock(), readcurrentstate=Mock())

    def tick(self, now):
        self.clock.return_value = now
        self.env['process_serial_queue'](self.bridge)

    def test_startup_and_five_minute_interval(self):
        self.tick(1000)
        self.bridge.serial.write.assert_called_once_with(b'\x03a?\r')
        for now in (1030, 1090, 1200, 1299):
            self.tick(now)
            self.bridge.alarm_status.heartbeat.assert_called_with(True)
        self.assertEqual(self.bridge.serial.write.call_count, 1)
        self.tick(1300)
        self.assertEqual(self.bridge.serial.write.call_count, 2)

    def test_silent_panel_expires_after_reply_grace(self):
        self.tick(1000)
        self.tick(1300)
        self.tick(1329)
        self.bridge.alarm_status.heartbeat.assert_called_with(True)
        self.tick(1330)
        self.bridge.alarm_status.heartbeat.assert_called_with(False)
        self.bridge._alarm_last_report = 1331
        self.tick(1331)
        self.bridge.alarm_status.heartbeat.assert_called_with(True)

    def test_disconnect_closed_port_and_passthrough(self):
        for setting in ('disconnect', 'closed', 'passthrough'):
            with self.subTest(setting=setting):
                self.settings.COMFORTCONNECTED = setting != 'disconnect'
                self.settings.PASSTHROUGH_ACTIVE = setting == 'passthrough'
                self.bridge.serial.is_open = setting != 'closed'
                self.tick(1000)
                self.bridge.alarm_status.heartbeat.assert_called_with(False)
                self.bridge.serial.write.assert_not_called()

    def test_successful_relogin_forces_snapshot(self):
        self.bridge._alarm_snapshot_due = 9999
        self.env['handle_serial_line'](self.bridge, '\x03LU01')
        self.assertEqual(self.bridge._alarm_snapshot_due, 0)
        self.tick(1000)
        self.bridge.serial.write.assert_called_once_with(b'\x03a?\r')

    def test_alarm_events_still_force_snapshot(self):
        for kind in ('AM', 'AR'):
            with self.subTest(kind=kind):
                self.bridge._alarm_snapshot_due = 9999
                self.env['comfort_protocol'] = SimpleNamespace(**{
                    'ComfortAMSystemAlarmReport': lambda _: SimpleNamespace(triggered=False, message='event'),
                    'ComfortARSystemAlarmReport': lambda _: SimpleNamespace(message='restore')})
                self.bridge.publish_alarm_message = Mock()
                self.env['handle_serial_line'](self.bridge, '\x03' + kind + '0301')
                self.assertEqual(self.bridge._alarm_snapshot_due, 0)

if __name__ == '__main__':
    unittest.main()
