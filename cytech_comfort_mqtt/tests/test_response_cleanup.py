import ast
import json
import logging
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

BASE = Path(__file__).resolve().parents[1] / 'rootfs' / 'comfort2'


class ResponseCleanupTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((BASE / 'bridge.py').read_text(encoding='utf-8-sig'))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Comfort2')
        methods = [node for node in cls.body if isinstance(node, ast.FunctionDef)
                   and node.name in {'on_connect', 'clear_response_discovery', 'publish_response_discovery'}]
        settings = SimpleNamespace(device_properties={}, DOMAIN='comfort', MAX_RESPONSES=1023,
            COMFORT_RESPONSES=5, response_properties={'1': {'Name': 'Test response'}},
            ALARMRESPONSECOMMANDTOPIC='comfort/response%d/set',
            ALARMAVAILABLETOPIC='comfort/alarm/online', ALARMCONNECTEDTOPIC='comfort/alarm/connected')
        env = {'settings': settings, 'logger': logging.getLogger('test.response'),
               'time': SimpleNamespace(sleep=Mock()), 'json': json}
        wrapper = ast.ClassDef(name='Bridge', bases=[], keywords=[], body=methods, decorator_list=[])
        exec(compile(ast.fix_missing_locations(ast.Module(body=[wrapper], type_ignores=[])), 'bridge.py', 'exec'), env)
        self.bridge = env['Bridge']()
        self.bridge.publish = Mock()
        self.bridge._responses_discovery_published = True

    def test_clear_removes_full_supported_range_and_resets_flag(self):
        b = self.bridge
        b.clear_response_discovery()
        self.assertFalse(b._responses_discovery_published)
        self.assertEqual(b.publish.call_count, 1023)
        b.publish.assert_any_call('homeassistant/button/comfort/response0001/config', None, qos=1, retain=True)
        b.publish.assert_any_call('homeassistant/button/comfort/response1023/config', None, qos=1, retain=True)

    def test_mqtt_startup_clears_responses_before_any_login_or_discovery(self):
        b = self.bridge
        for name in ('input', 'output', 'flag', 'counter', 'sensor', 'timer'):
            setattr(b, 'clear_' + name + '_discovery', Mock())
        # Stop the real callback immediately after its startup-cleanup block.
        b.clear_battery_voltage_discovery = Mock(side_effect=StopIteration)
        with self.assertRaises(StopIteration):
            b.on_connect(None, None, {}, 'Success', None)
        self.assertEqual(b.publish.call_count, 1023)
        self.assertFalse(b._responses_discovery_published)

    def test_republish_preserves_availability_and_named_button(self):
        b = self.bridge
        b.clear_response_discovery()
        b.publish.reset_mock()
        b.publish_response_discovery({'identifiers': ['comfort']})
        b.publish.assert_called_once()
        topic, encoded = b.publish.call_args.args
        self.assertEqual(topic, 'homeassistant/button/comfort/response0001/config')
        payload = json.loads(encoded)
        self.assertEqual(payload['name'], 'Test response')
        self.assertEqual(payload['availability_mode'], 'all')
        self.assertEqual({item['topic'] for item in payload['availability']},
                         {'comfort/alarm/online', 'comfort/alarm/connected'})


if __name__ == '__main__':
    unittest.main()
