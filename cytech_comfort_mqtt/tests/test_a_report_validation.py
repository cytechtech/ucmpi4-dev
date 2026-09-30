import ast
import logging
import re
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

BASE=Path(__file__).resolve().parents[1]/'rootfs'/'comfort2'

class AReportValidationTests(unittest.TestCase):
    def setUp(self):
        tree=ast.parse((BASE/'bridge.py').read_text(encoding='utf-8-sig'))
        method=next(n for c in tree.body if isinstance(c,ast.ClassDef) for n in c.body
                    if isinstance(n,ast.FunctionDef) and n.name=='handle_serial_line')
        tree=ast.parse((BASE/'comfort_protocol.py').read_text(encoding='utf-8-sig'))
        parser=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Comfort_A_SecurityInformationReport')
        env=dict(re=re,time=time,logging=logging,logger=Mock(),settings=SimpleNamespace(ALARMSTATUSTOPIC='status'))
        exec(compile(ast.Module(body=[parser],type_ignores=[]),'parser','exec'),env)
        self.parse=Mock(wraps=env['Comfort_A_SecurityInformationReport'])
        env['comfort_protocol']=SimpleNamespace(Comfort_A_SecurityInformationReport=self.parse)
        exec(compile(ast.Module(body=[method],type_ignores=[]),'handler','exec'),env)
        self.handle=env['handle_serial_line']
        self.logger=env['logger']
        self.bridge=SimpleNamespace(alarm_status=SimpleNamespace(snapshot=Mock()),publish=Mock())

    def test_incomplete_and_nonhex_replies_are_ignored_before_parsing(self):
        for reply in ('a?03','a?03012000000','a?','a?03012000000000000Z'):
            with self.subTest(reply=reply):
                self.handle(self.bridge,'\x03'+reply)
        self.parse.assert_not_called()
        self.bridge.alarm_status.snapshot.assert_not_called()
        self.bridge.publish.assert_not_called()
        self.assertEqual(self.logger.warning.call_count,4)

    def test_valid_then_partial_then_valid_preserves_snapshot_and_recovers(self):
        self.handle(self.bridge,'\x03a?030120000000000000')
        first=self.bridge.alarm_status.snapshot.call_args.args[0]
        self.assertEqual(first.state,'Trouble')
        self.assertEqual(first.XX,32)
        self.handle(self.bridge,'\x03a?03')
        self.bridge.alarm_status.snapshot.assert_called_once_with(first)
        self.bridge.publish.assert_called_once_with('status','Trouble',qos=2,retain=True)
        self.handle(self.bridge,'\x03a?000000000000000000')
        self.assertEqual(self.bridge.alarm_status.snapshot.call_count,2)
        self.bridge.publish.assert_called_with('status','Idle',qos=2,retain=True)

if __name__=='__main__': unittest.main()
