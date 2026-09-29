import ast
import io
import logging
import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

BASE = Path(__file__).resolve().parents[1] / 'rootfs' / 'comfort2'
if not BASE.exists():
    BASE = Path(__file__).parent


def load_bridge():
    tree = ast.parse((BASE / 'bridge.py').read_text(encoding='utf-8-sig'))
    original = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Comfort2')
    names = {'login', 'handle_serial_line', 'on_message', 'publish_alarm_message', 'startup_reload_when_ready'}
    nodes = [n for n in original.body if isinstance(n, ast.FunctionDef) and n.name in names]
    cls = ast.ClassDef(name='Bridge', bases=[], keywords=[], body=nodes, decorator_list=[])
    settings = SimpleNamespace(BROKERCONNECTED=True, COMFORTCONNECTED=False, FIRST_LOGIN=True,
        ALARMCONNECTEDTOPIC='connected', ALARMCOMMANDTOPIC='command', ALARMAVAILABLETOPIC='available',
        ALARMLWTTOPIC='lwt', REFRESHTOPIC='refresh', ALARMMESSAGETOPIC='message',
        ALARMLOGCLEARTOPIC='clear', RELOADTOPIC='reload', DOMAIN='comfort',
        ALARMSTATETOPIC='state', MQTT_DEVICE_COMFORT=None)
    env = {'settings': settings, 'logger': logging.getLogger('test.login'),
           'time': SimpleNamespace(sleep=Mock(), monotonic=Mock(return_value=100)),
           'threading': SimpleNamespace(Timer=Mock()), 'datetime': datetime,
           'comfort_protocol': SimpleNamespace(ComfortLUUserLoggedIn=lambda text: SimpleNamespace(user=int(text[2:4],16)))}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])), 'bridge.py', 'exec'), env)
    bridge = env['Bridge']()
    bridge.publish = Mock()
    bridge.alarm_log = Mock()
    bridge.alarm_status = Mock()
    bridge.serial = Mock()
    bridge.setdatetime = Mock()
    bridge.readcurrentstate = Mock()
    bridge._handle_reload_request = Mock()
    bridge.comfort_pincode = '987654'
    bridge.connected = False
    bridge._login_pending = False
    bridge._login_error = None
    return bridge, env


class LoginReportingTests(unittest.TestCase):
    def setUp(self):
        self.bridge, self.env = load_bridge()

    def test_login_waits_for_ack_and_rejection_reaches_both_logs(self):
        b = self.bridge
        b.login()
        self.assertFalse(b.connected)
        self.assertFalse(self.env['settings'].COMFORTCONNECTED)
        self.assertTrue(b._login_pending)
        b.serial.write.assert_called_once_with(b'\x03LI987654\r')
        with self.assertLogs('test.login', level='ERROR') as logs:
            b.handle_serial_line('\x03LU00')
        self.assertIn('Comfort login rejected', logs.output[0])
        self.assertNotIn('987654', str(logs.output))
        b.publish.assert_any_call('message', b._login_error, qos=2, retain=True)
        b.alarm_log.add.assert_called_with(b._login_error, level='MSG')
        b.alarm_status.heartbeat.assert_called_with(False)
        self.assertFalse(b.connected)

    def test_unsolicited_logout_is_not_reported_as_wrong_code(self):
        b = self.bridge
        b.connected = True
        with self.assertLogs('test.login', level='WARNING') as logs:
            b.handle_serial_line('\x03LU00')
        self.assertIn('session logged out', logs.output[0])
        self.assertNotIn('rejected', logs.output[0])
        self.assertFalse(b.connected)
        b.publish.assert_any_call('connected', '0', qos=2, retain=True)

    def test_failure_before_broker_still_records_diagnostic(self):
        b = self.bridge
        self.env['settings'].BROKERCONNECTED = False
        del b.alarm_log
        b._login_pending = True
        with self.assertLogs('test.login', level='ERROR'):
            b.handle_serial_line('\x03LU00')
        self.assertIn('comfort_login_id', b._login_error)
        b.publish.assert_any_call('message', b._login_error, qos=2, retain=True)

    def test_success_clears_rejection_without_publishing_fake_command(self):
        b = self.bridge
        b._login_error = 'Comfort login rejected'
        b.login()
        b.handle_serial_line('\x03LU01')
        self.assertIsNone(b._login_error)
        self.assertTrue(b.connected)
        self.assertTrue(self.env['settings'].COMFORTCONNECTED)
        b.publish.assert_any_call('message', 'Comfort login successful', qos=2, retain=True)
        self.assertFalse(any(call.args[0] == 'command' for call in b.publish.call_args_list))
        b.readcurrentstate.assert_called_once()

    def test_retained_commands_are_ignored_before_logging_or_execution(self):
        b = self.bridge
        b.connected = True
        for payload in (b'comm test', b'ARM_AWAY', b'DISARM 987654'):
            with self.assertLogs('test.login', level='WARNING'):
                b.on_message(None, None, SimpleNamespace(topic='command', payload=payload, retain=True))
        b.alarm_log.add.assert_not_called()
        b.serial.write.assert_not_called()
        b.publish.assert_not_called()

    def test_live_disarm_still_works_without_logging_pin(self):
        b = self.bridge
        b.connected = True
        with self.assertLogs('test.login', level='DEBUG') as logs:
            b.on_message(None, None, SimpleNamespace(topic='command', payload=b'DISARM 987654', retain=False))
        b.serial.write.assert_called_once_with(b'\x03m!00987654\r')
        self.assertNotIn('987654', str(logs.output))
        b.alarm_log.add.assert_called_with('DISARM', level='CMD')

    def test_startup_warning_is_throttled_and_actionable(self):
        b = self.bridge
        b._login_error = 'Comfort login rejected - check Comfort user code'
        with self.assertLogs('test.login', level='WARNING') as logs:
            b.startup_reload_when_ready()
            b.startup_reload_when_ready()
        self.assertEqual(len(logs.output), 1)
        self.assertIn('check Comfort user code', logs.output[0])
        self.assertEqual(self.env['threading'].Timer.call_count, 2)
        self.env['settings'].MQTT_DEVICE_COMFORT = {'name': 'Comfort'}
        b.startup_reload_when_ready()
        b._handle_reload_request.assert_called_once()

    def test_serial_logging_redacts_codes_but_preserves_wire_bytes(self):
        tree = ast.parse((BASE / 'bridge.py').read_text(encoding='utf-8-sig'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'LoggedSerial')
        wire = Mock()
        class Serial:
            def write(self, data):
                wire(data)
                return len(data)
        env = {'serial': SimpleNamespace(Serial=Serial), 'logger': logging.getLogger('test.serial'), 're': re}
        exec(compile(ast.Module(body=[cls], type_ignores=[]), 'bridge.py', 'exec'), env)
        serial = env['LoggedSerial']()
        for command in (b'\x03LI987654\r', b'\x03m!00987654\r', b'\x03M!01987654\r'):
            with self.assertLogs('test.serial', level='DEBUG') as logs:
                serial.write(command)
            wire.assert_called_with(command)
            self.assertNotIn('987654', str(logs.output))
            self.assertIn('[redacted]', str(logs.output))


class LoggingTests(unittest.TestCase):
    def test_ram_log_follows_level_without_stdout_or_duplicate_handlers(self):
        env = {'__name__': 'isolated_logging_config'}
        exec(compile((BASE / 'logging_config.py').read_text(encoding='utf-8-sig'), 'logging_config.py', 'exec'), env)
        root = logging.getLogger('test.isolated_logging_setup')
        root.propagate = False
        stream = io.StringIO()
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as folder:
            env['RAM_LOG_FILE'] = str(Path(folder) / 'bridge.log')
            try:
                with patch.object(logging, 'getLogger', return_value=root), patch('sys.stdout', stream), patch('sys.stderr', stderr):
                    env['setup_ram_logging'](logging.INFO)
                    root.debug('hidden debug')
                    root.error('login rejected')
                    env['setup_ram_logging'](logging.DEBUG)
                    env['setup_ram_logging'](logging.DEBUG)
                    root.debug('visible debug')
                self.assertEqual(len(root.handlers), 1)
                self.assertEqual(stream.getvalue(), '')
                self.assertEqual(stderr.getvalue(), '')
                contents = Path(env['RAM_LOG_FILE']).read_text()
                self.assertNotIn('hidden debug', contents)
                self.assertEqual(contents.count('login rejected'), 1)
                self.assertIn('visible debug', contents)
            finally:
                for handler in root.handlers:
                    handler.close()
                root.handlers.clear()


if __name__ == '__main__':
    unittest.main()
