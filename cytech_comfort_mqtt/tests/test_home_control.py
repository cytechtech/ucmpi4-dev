import json
import logging
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'rootfs' / 'comfort2'))
from home_control_protocol import query, action, decode
from home_control_models import parse_home_control
from home_control import HomeControl
from home_control_mqtt import HomeControlMqtt
from cclx_parser import parse_cclx

XML = '''<Configuration><Counters><Counter Number="3" Name="Curtain"/></Counters><ControlMenuGroups><ControlMenuGroup Number="2" PhraseWord1="Room">
<ControlMenuItems><ControlMenuItem Number="4" AlternativePhrase="Curtain" FeedbackType="Counter" FeedbackName="Curtain">
<ControlMenuSubItems><ControlMenuSubItem Number="0" PhraseWord1="Open" ResponseName="Open"/>
<ControlMenuSubItem Number="1" PhraseWord1="Close"/><ControlMenuSubItem Number="10"/>
</ControlMenuSubItems></ControlMenuItem>
<ControlMenuItem Number="5" PhraseWord1="Scene" FeedbackType="None"/>
</ControlMenuItems></ControlMenuGroup></ControlMenuGroups></Configuration>'''


class HomeControlTests(unittest.TestCase):
    def setUp(self):
        self.controls, self.errors = parse_home_control(ET.fromstring(XML))
        self.publish = Mock()
        self.service = HomeControl(self.publish)
        self.service.configure(self.controls)

    def test_wire_commands_and_validation(self):
        self.assertEqual(query(2, 4), 'CM0204')
        self.assertEqual(action(2, 4, 0), 'CM020400')
        for args in [(6, 0), (0, 10), (-1, 0), (True, 0)]:
            with self.assertRaises(ValueError):
                query(*args)
        with self.assertRaises(ValueError):
            action(0, 0, 10)

    def test_feedback_lengths_and_signed_sensor_values(self):
        for raw, expected in [('', None), ('80', 128), ('8000', 128), ('0010', 4096),
                              ('F0FF', -16), ('FFFF', -1), ('0080', -32768), ('FF7F', 32767)]:
            self.assertEqual(decode('cm0204' + raw).value(True), expected)
        self.assertEqual(decode('cm0204FF').value(), 255)
        for bad in ['CM020400', 'cm02040', 'cm0204000010', 'cm0600', 'cm0204GG']:
            with self.assertRaises(ValueError):
                decode(bad)

    def test_parser_excludes_placeholders_and_other_menus(self):
        self.assertFalse(self.errors)
        c = self.controls[2, 4]
        self.assertEqual(c.label, 'Curtain')
        self.assertEqual([a.number for a in c.actions], [0, 1])
        self.assertEqual(c.actions[1].response, '')

    def test_paced_initialisation_and_no_action_replay(self):
        send = Mock()
        self.service.start()
        self.service.command(2, 4, 0)
        self.service.tick(1, True, send)
        send.assert_called_once_with(b'\x03CM0204\r')
        self.service.tick(1.01, True, send)
        self.assertEqual(send.call_count, 1)
        self.service.tick(1.2, True, send)
        send.assert_called_with(b'\x03CM020400\r')
        self.service.command(2, 4, 1)
        self.service.start(False)
        self.service.start()
        self.assertEqual(list(self.service.pending), ['CM0204'])

    def test_unsolicited_and_no_feedback(self):
        self.service.start()
        self.service.receive('cm0204FF')
        self.publish.assert_called_with(self.controls[2, 4], 255, 'FF')
        self.service.receive('cm0204')
        self.publish.assert_called_with(self.controls[2, 4], None, '')
        self.service.start(False)
        self.publish.reset_mock()
        self.service.receive('cm020400')
        self.publish.assert_not_called()

    def test_reload_discards_stale_work(self):
        self.service.start()
        self.service.command(2, 4, 0)
        self.service.configure({})
        self.assertFalse(self.service.pending)
        with self.assertRaises(ValueError):
            self.service.command(2, 4, 0)

    def test_mqtt_discovery_and_command_rejection(self):
        client = Mock()
        adapter = HomeControlMqtt(client, 'comfort')
        adapter.discovery(self.controls, {'identifiers': ['comfort']}, [])
        configs = [(t, json.loads(p)) for (t, p), kw in client.publish.call_args_list if t.endswith('/config')]
        self.assertEqual(len(configs), 4)
        self.assertEqual(configs[1][1]['state_topic'], 'comfort/home_control/02/04/state')
        self.service.start()
        msg = SimpleNamespace(topic='comfort/home_control/02/04/set', payload=b'0', retain=False)
        adapter.command(msg, self.service)
        self.assertEqual(self.service.pending[-1], 'CM020400')
        for payload, retained in [(b'10', False), (b'0', True), (b'9', False)]:
            msg.payload, msg.retain = payload, retained
            with self.assertRaises(ValueError):
                adapter.command(msg, self.service)

    def test_xml_parse_failure_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.cclx'
            path.write_text('<bad>')
            result = parse_cclx(path, check_zone_name=lambda _: True,
                                check_index_number=lambda *_: True, logger=logging.getLogger('test'))
            self.assertIsNotNone(result.parse_error)

    def test_x10_and_invalid_actions(self):
        root = ET.fromstring(XML)
        root.find('.//ControlMenuItem').set('FeedbackType', 'X10')
        controls, errors = parse_home_control(root)
        self.assertNotIn((2, 4), controls)
        root = ET.fromstring(XML)
        root.find('.//ControlMenuSubItem').set('Number', '10')
        controls, errors = parse_home_control(root)
        self.assertTrue(errors)
        self.assertNotIn((2, 4), controls)

    def test_cleanup_covers_removed_entities_and_state(self):
        client = Mock()
        HomeControlMqtt(client, 'comfort').clear()
        client.publish.assert_any_call('homeassistant/button/comfort/home_control_05_09_9/config', None, qos=1, retain=True)
        client.publish.assert_any_call('comfort/home_control/02/04/state', None, qos=1, retain=True)


if __name__ == '__main__':
    unittest.main()
