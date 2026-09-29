import ast
import json
import time
import unittest
import sys
from pathlib import Path
from types import SimpleNamespace
ADDON = Path(__file__).resolve().parents[1]
BASE = ADDON / 'rootfs' / 'comfort2'
DASHBOARD = ADDON / 'home_assistant' / 'dashboards' / 'includes'
PACKAGE = ADDON / 'home_assistant' / 'packages'
sys.path.insert(0, str(BASE))
import yaml
from jinja2 import Environment, StrictUndefined
import alarm_status

protocol_tree = ast.parse((BASE / 'comfort_protocol.py').read_text(encoding='utf-8-sig'))
settings = SimpleNamespace(ZONEMAPFILE=False, input_properties={'1': {'Name': '<Test Zone>'}})
ns = {'settings': settings}
classes = [n for n in protocol_tree.body if isinstance(n, ast.ClassDef) and n.name in {
    'ComfortAMSystemAlarmReport', 'ComfortARSystemAlarmReport', 'Comfort_A_SecurityInformationReport'}]
exec(compile(ast.Module(body=classes, type_ignores=[]), 'comfort_protocol.py', 'exec'), ns)


class AlarmTests(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.tracker = alarm_status.AlarmStatusTracker(
            lambda payload: self.sent.append(json.loads(json.dumps(payload))),
            ns['ComfortAMSystemAlarmReport'].triggers_ha,
        )
        self.tracker.heartbeat(True)

    def report(self, code, parameter=1, restore=False):
        kind = 'AR' if restore else 'AM'
        return ns[f'Comfort{kind}SystemAlarmReport'](f'{kind}{code:02X}{parameter:02X}')

    def test_policy_all_codes(self):
        excluded = {1,2,3,4,7,8,9,12,13,15,17,19,22,23,24,25,26}
        for mapped in (False, True):
            settings.ZONEMAPFILE = mapped
            for code in range(256):
                report = self.report(code)
                self.assertEqual(report.triggered, code not in excluded)
                self.assertEqual(report.triggered, ns['ComfortAMSystemAlarmReport'].triggers_ha(code))
        settings.ZONEMAPFILE = False

    def test_multiple_devices_restore_independently(self):
        self.tracker.event(self.report(2, 1))
        self.tracker.event(self.report(2, 33))
        self.tracker.event(self.report(2, 1, True), True)
        self.assertEqual(self.tracker.rows['2']['status'], 'Active')
        self.tracker.event(self.report(2, 33, True), True)
        self.assertEqual(self.tracker.rows['2']['status'], 'Cleared')

    def test_snapshot_and_unidentified_device(self):
        self.tracker.snapshot(SimpleNamespace(XX=2))
        self.assertEqual(self.tracker.rows['2']['status'], 'Active')
        self.tracker.event(self.report(2, 1, True), True)
        self.assertEqual(self.tracker.rows['2']['status'], 'Unknown')
        self.tracker.snapshot(SimpleNamespace(XX=0))
        self.assertEqual(self.tracker.rows['2']['status'], 'Cleared')

    def test_bit_mapping(self):
        for code, bit in alarm_status.TROUBLE_BITS.items():
            self.tracker.snapshot(SimpleNamespace(XX=1 << bit))
            for other in alarm_status.TROUBLE_BITS:
                self.assertEqual(self.tracker.rows[str(other)]['status'], 'Active' if code == other else 'Cleared')

    def test_events_not_latched_as_faults(self):
        for code in (0, 5, 7, 20, 21, 24, 26, 255):
            self.tracker.event(self.report(code))
            self.assertEqual(self.tracker.rows[str(code)]['status'], 'Event received')

    def test_restart_disconnect_and_heartbeat(self):
        self.tracker.event(self.report(1))
        self.assertEqual(self.sent[-1]['status'], 'online')
        self.tracker.heartbeat(False)
        self.assertEqual(self.sent[-1]['status'], 'offline')
        self.assertTrue(all(row['status'] == 'Unknown' for row in self.sent[-1]['rows']))
        self.tracker.heartbeat(True)
        before = len(self.sent)
        self.tracker.heartbeat(True)
        self.assertEqual(len(self.sent), before)
        self.tracker.last_write -= 6
        self.tracker.heartbeat(True)
        self.assertEqual(len(self.sent), before + 1)
        self.tracker.reset()
        self.assertEqual(self.tracker.rows, {})
        self.assertEqual(self.sent[-1]['status'], 'offline')

    def test_dashboard_template_live_offline_and_escaping(self):
        view = yaml.safe_load((DASHBOARD / 'alarm_status_view.yaml').read_text(encoding='utf-8'))
        template = Environment(undefined=StrictUndefined).from_string(view['cards'][0]['content'])
        self.tracker.event(self.report(3))
        self.tracker.event(self.report(255))
        self.tracker.rows['3']['message'] = '<script>alert(1)</script> | fault'
        data = self.tracker.payload()
        self.assertEqual(len(data['rows']), 28)
        self.assertFalse(data['rows'][3]['triggers'])
        self.assertEqual(data['rows'][3]['status'], 'Active')
        def render(live, rows):
            return template.render(is_state=lambda *_: live, state_attr=lambda *_: rows)
        page = render(True, data['rows'])
        self.assertIn('🔴 Active', page)
        self.assertNotIn('<script>', page)
        self.assertIn('&lt;script&gt;', page)
        offline = render(False, data['rows'])
        self.assertNotIn('🔴 Active', offline)
        self.assertIn('Last known: Active', offline)
        self.assertIn('Waiting for', render(False, None))

    def test_yaml_navigation_and_sensor_expiry(self):
        button = yaml.safe_load((DASHBOARD / 'alarm_status_button.yaml').read_text(encoding='utf-8'))
        view = yaml.safe_load((DASHBOARD / 'alarm_status_view.yaml').read_text(encoding='utf-8'))
        package = yaml.safe_load((PACKAGE / 'comfort_am_status.yaml').read_text(encoding='utf-8'))
        self.assertEqual(button['tap_action']['navigation_path'], '/comfort-alarm/' + view['path'])
        self.assertTrue(view['subview'])
        self.assertEqual(package['mqtt']['sensor'][0]['expire_after'], 45)

    def test_mqtt_failure_does_not_interrupt_alarm_handling(self):
        self.tracker.publish = lambda _: (_ for _ in ()).throw(OSError('offline'))
        with self.assertLogs('alarm_status', level='ERROR'):
            self.tracker.event(self.report(3))
        self.assertEqual(self.tracker.rows['3']['status'], 'Active')

    def test_bridge_real_handlers_preserve_mqtt_behavior(self):
        tree = ast.parse((BASE / 'bridge.py').read_text(encoding='utf-8-sig'))
        method = next(n for cls in tree.body if isinstance(cls, ast.ClassDef)
                      for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'handle_serial_line')
        env = {'time': time, 'comfort_protocol': SimpleNamespace(**ns),
               'settings': SimpleNamespace(ALARMSTATETOPIC='alarm'),
               'logger': __import__('logging').getLogger('test')}
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'bridge.py', 'exec'), env)
        publications, messages = [], []
        bridge = SimpleNamespace(alarm_status=self.tracker,
                                 publish=lambda *args, **kwargs: publications.append((args, kwargs)),
                                 publish_alarm_message=lambda text, **kwargs: messages.append(text))
        env['handle_serial_line'](bridge, '\x03AM0301')
        self.assertEqual(publications, [])
        self.assertEqual(messages, ['Power Failure - Main'])
        self.assertEqual(self.tracker.rows['3']['status'], 'Active')
        env['handle_serial_line'](bridge, '\x03AR0301')
        self.assertEqual(self.tracker.rows['3']['status'], 'Cleared')
        env['handle_serial_line'](bridge, '\x03AM1401')
        self.assertEqual(publications[-1][0], ('alarm', 'triggered'))
        self.assertEqual(messages[-2:], ['Fire', 'triggered'])

    def test_source_syntax(self):
        for name in ('comfort_protocol.py', 'bridge.py', 'alarm_status.py'):
            ast.parse((BASE / name).read_text(encoding='utf-8-sig'))


if __name__ == '__main__':
    unittest.main()
