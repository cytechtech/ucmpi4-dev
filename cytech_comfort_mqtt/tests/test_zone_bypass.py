import ast
import json
import logging
import re
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

BASE = Path(__file__).resolve().parents[1] / 'rootfs' / 'comfort2'

class ZoneBypassTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((BASE / 'bridge.py').read_text(encoding='utf-8-sig'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Comfort2')
        methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in {
            'handle_zone_bypass_command', 'publish_zone_bypass_discovery', 'publish_zone_bypass_state', 'publish_input_discovery'}]
        self.settings = SimpleNamespace(DOMAIN='comfort', COMFORT_INPUTS=96, COMFORTCONNECTED=True,
            PASSTHROUGH_ACTIVE=False, ALARMAVAILABLETOPIC='available', ALARMCONNECTEDTOPIC='connected')
        env = dict(time=SimpleNamespace(sleep=Mock()), settings=self.settings, re=re, json=json, datetime=datetime, logger=logging.getLogger('test.bypass'))
        wrapper=ast.ClassDef(name='Bridge', bases=[], keywords=[], body=methods, decorator_list=[])
        exec(compile(ast.fix_missing_locations(ast.Module(body=[wrapper], type_ignores=[])), 'bridge.py','exec'),env)
        self.bridge=env['Bridge']()
        self.bridge.connected=True
        self.bridge.serial=SimpleNamespace(is_open=True, write=Mock())
        self.bridge.publish=Mock()

    def command(self, zone='10', action=b'SET', retain=False):
        self.bridge.handle_zone_bypass_command(SimpleNamespace(topic=f'comfort/zone/{zone}/bypass/set',payload=action,retain=retain))

    def test_commands_use_hex_and_request_confirmation_without_optimistic_state(self):
        self.command()
        self.command(action=b'CLEAR')
        self.assertEqual([c.args[0] for c in self.bridge.serial.write.call_args_list],
            [b'\x03DA4B0A\r',b'\x03B?0A\r',b'\x03DA4C0A\r',b'\x03B?0A\r'])
        self.bridge.publish.assert_not_called()

    def test_invalid_retained_and_offline_requests_never_send(self):
        for zone in ('0','97','-1','oops'):
            self.command(zone=zone)
        self.command(action=b'toggle')
        self.command(retain=True)
        self.bridge.connected=False
        self.command()
        self.bridge.connected=True
        self.settings.PASSTHROUGH_ACTIVE=True
        self.command()
        self.bridge.serial.write.assert_not_called()

    def test_discovery_has_two_nonretained_buttons_and_confirmed_sensor(self):
        self.bridge.publish_zone_bypass_discovery(10,'Front Door',{'identifiers':['comfort']})
        payloads=[json.loads(c.args[1]) for c in self.bridge.publish.call_args_list]
        self.assertEqual(len(payloads),3)
        self.assertEqual(payloads[0]['state_topic'],'comfort/zone/10/bypass/state')
        self.assertEqual([p['payload_press'] for p in payloads[1:]],['SET','CLEAR'])
        self.assertTrue(all(p['retain'] is False for p in payloads[1:]))
        self.assertTrue(all(p['availability_mode']=='all' for p in payloads))

    def test_confirmed_nonzero_state(self):
        self.bridge.publish_zone_bypass_state(10,2)
        self.bridge.publish.assert_called_with('comfort/zone/10/bypass/state','Bypassed',qos=1,retain=True)
        self.bridge.publish_zone_bypass_state(10,0)
        self.bridge.publish.assert_called_with('comfort/zone/10/bypass/state','Not bypassed',qos=1,retain=True)

    def test_discovery_requests_bulk_status_after_publishing_entities(self):
        self.settings.COMFORT_INPUTS=2
        self.settings.ZONEMAPFILE=False
        self.settings.ALARMINPUTTOPIC='comfort/input%d'
        events=[]
        self.bridge.publish.side_effect=lambda *a, **k: events.append('publish')
        self.bridge.serial.write.side_effect=lambda value: events.append(value)
        self.bridge.publish_input_discovery({'identifiers':['comfort']})
        self.assertEqual(events.count('publish'),8)
        self.assertEqual(events[-1],b'\x03b?00\r')
        self.bridge.serial.write.assert_called_once_with(b'\x03b?00\r')

    def test_discovery_never_queries_offline_or_in_passthrough(self):
        self.settings.COMFORT_INPUTS=1
        self.settings.ZONEMAPFILE=False
        self.settings.ALARMINPUTTOPIC='comfort/input%d'
        self.bridge.connected=False
        self.bridge.publish_input_discovery({})
        self.bridge.connected=True
        self.settings.PASSTHROUGH_ACTIVE=True
        self.bridge.publish_input_discovery({})
        self.settings.PASSTHROUGH_ACTIVE=False
        self.bridge.serial.is_open=False
        self.bridge.publish_input_discovery({})
        self.bridge.serial.write.assert_not_called()

    def test_protocol_bulk_bit_order_and_nonzero_by(self):
        tree=ast.parse((BASE/'comfort_protocol.py').read_text(encoding='utf-8-sig'))
        nodes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name in {'ComfortBYBypassActivationReport','ComfortB_ReportAllBypassZones'}]
        self.settings.BYPASSEDZONES=[]
        self.settings.BypassCache={}
        env=dict(settings=self.settings,logger=logging.getLogger('test.bypass'))
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'protocol.py','exec'),env)
        env['ComfortB_ReportAllBypassZones']('b?00010204')
        self.assertEqual(self.settings.BYPASSEDZONES,[1,10,19])
        env['ComfortBYBypassActivationReport']('BY0502')
        self.assertIn(5,self.settings.BYPASSEDZONES)
        env['ComfortBYBypassActivationReport']('B?0500')
        self.assertNotIn(5,self.settings.BYPASSEDZONES)
        before=list(self.settings.BYPASSEDZONES)
        env['logger']=Mock()
        for report in ('BY0500','B?0500','BY0600','B?0600'):
            env['ComfortBYBypassActivationReport'](report)
        self.assertEqual(self.settings.BYPASSEDZONES,before)
        env['logger'].debug.assert_not_called()


if __name__=='__main__':
    unittest.main()
