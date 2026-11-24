import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import linux_cli
import qwen_client


class LinuxLauncherTests(unittest.TestCase):
    def test_offline_flag_overrides_requested_network_action(self):
        for flag in ('--self-check','--validate-only'):
            with patch.object(linux_cli,'run_action',return_value=0) as action:
                self.assertEqual(linux_cli.main(['batch56',flag]),0)
            action.assert_called_once_with('selfcheck')

    def test_file_check_makes_no_http_request(self):
        with patch.object(qwen_client,'http',side_effect=AssertionError('must not connect')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(linux_cli.self_check(),0)

    def test_menu_exit_does_not_run_an_experiment(self):
        with patch('builtins.input',return_value='0'),patch.object(linux_cli,'run_action',side_effect=AssertionError('must not call')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(linux_cli.main([]),0)

    def test_failure_keeps_diagnostic_and_returns_failure(self):
        with tempfile.TemporaryDirectory() as name,patch.object(linux_cli,'ROOT',Path(name)), \
             patch.object(linux_cli,'dispatch',side_effect=ValueError('controlled test error')), \
             contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(linux_cli.run_action('check'),2)
            logs=list((Path(name)/'records'/'linux-launch').glob('*.log'))
            self.assertEqual(len(logs),1)
            self.assertIn('ValueError: controlled test error',logs[0].read_text(encoding='utf-8'))

    def test_missing_private_history_has_a_clear_error(self):
        with patch.object(linux_cli,'HISTORY',Path('this-fixture-does-not-exist.json')):
            with self.assertRaisesRegex(ValueError,'리눅스 ZIP'):
                linux_cli.dispatch('batch43',[])

    def test_previous_arguments_are_restored_after_an_error(self):
        previous=linux_cli.sys.argv
        def fail(): raise ValueError('fixture')
        with self.assertRaises(ValueError): linux_cli._call(fail,['temporary'])
        self.assertIs(linux_cli.sys.argv,previous)


if __name__=='__main__': unittest.main()
