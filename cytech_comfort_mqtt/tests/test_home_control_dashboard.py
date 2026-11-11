import importlib.util
import json
from pathlib import Path
import sys
import unittest
from xml.etree import ElementTree as ET

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'rootfs' / 'comfort2'))
from home_control_models import parse_home_control
from home_control_mqtt import HomeControlMqtt
from unittest.mock import Mock
import yaml
from jinja2 import Environment

spec = importlib.util.spec_from_file_location('dashboard_generator', BASE / 'home_assistant' / 'generate_home_control_dashboard.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class DashboardTests(unittest.TestCase):
    def test_dashboard_references_match_discovery_defaults_for_custom_domain(self):
        root = ET.fromstring('''<Configuration><ControlMenuGroups><ControlMenuGroup Number="0">
        <ControlMenuItems><ControlMenuItem Number="2" PhraseWord1="Lamp" FeedbackType="Sensor">
        <ControlMenuSubItems><ControlMenuSubItem Number="1" PhraseWord1="On"/></ControlMenuSubItems>
        </ControlMenuItem></ControlMenuItems></ControlMenuGroup></ControlMenuGroups></Configuration>''')
        controls, _ = parse_home_control(root)
        result = generator.dashboard(controls, 'custom')
        rows = result['views'][0]['cards'][1]['entities']
        client = Mock()
        HomeControlMqtt(client, 'custom').discovery(controls, {}, [])
        ids = {json.loads(call.args[1])['default_entity_id'] for call in client.publish.call_args_list
               if call.args[0].endswith('/config') and not call.args[0].endswith('/home_control_menu/config')}
        self.assertEqual({row['entity'] for row in rows}, ids)

    def test_installed_dashboard_is_independent_of_cclx(self):
        result = yaml.safe_load((BASE / 'home_assistant' / 'dashboards' / 'home_control.yaml').read_text(encoding='utf-8'))
        self.assertEqual(result['views'][0]['cards'], [
            {'type': 'custom:comfort-home-control-card', 'domain': 'cytech_comfort_mqtt'}])

    def test_menu_discovery_templates_and_empty_reload(self):
        client = Mock()
        adapter = HomeControlMqtt(client, 'custom')
        adapter.discovery({}, {}, [])
        configs = [json.loads(c.args[1]) for c in client.publish.call_args_list if c.args[0].endswith('/config')]
        menu = configs[0]
        env = Environment()
        payload = {'items': []}
        self.assertEqual(env.from_string(menu['value_template']).render(value_json=payload), '0')
        attrs = json.loads(env.from_string(menu['json_attributes_template']).render(value_json=payload))
        self.assertEqual(attrs, {'items': [], 'comfort_home_control_menu': 'custom'})

    def test_entity_identity_is_stable_across_labels(self):
        root = ET.fromstring('''<Configuration><ControlMenuGroups><ControlMenuGroup Number="0">
        <ControlMenuItems><ControlMenuItem Number="2" PhraseWord1="Lamp" FeedbackType="Sensor">
        <ControlMenuSubItems><ControlMenuSubItem Number="1" PhraseWord1="On"/></ControlMenuSubItems>
        </ControlMenuItem></ControlMenuItems></ControlMenuGroup></ControlMenuGroups></Configuration>''')
        controls, _ = parse_home_control(root)
        client = Mock()
        HomeControlMqtt(client, 'custom').discovery(controls, {}, [])
        configs = [json.loads(c.args[1]) for c in client.publish.call_args_list if c.args[0].endswith('/config')]
        env = Environment()
        identities = [json.loads(env.from_string(c['json_attributes_template']).render(value_json={'items': []}))
                      for c in configs[1:]]
        self.assertEqual(identities, [{'comfort_home_control': 'custom:0:2:state'},
                                      {'comfort_home_control': 'custom:0:2:1'}])

    def test_empty_configuration_produces_explanatory_view(self):
        self.assertIn('No Home Control', generator.dashboard({})['views'][0]['cards'][0]['content'])
