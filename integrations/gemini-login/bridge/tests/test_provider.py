"""Hermes profile/client tests; all subprocess responses here are local fixtures."""
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import threading
import subprocess
import signal
import time
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
HERMES = pathlib.Path.home() / '.hermes/hermes-agent'
sys.path.insert(0, str(HERMES))
sys.path.insert(0, str(ROOT))


def provider():
    import provider as package
    return package


class ProfileTests(unittest.TestCase):
    def test_external_process_profile_registers_exact_models_and_text_only(self):
        self.assertTrue((ROOT / 'provider/__init__.py').exists(), 'provider plugin not implemented')
        package = provider()
        from providers import get_provider_profile
        with tempfile.TemporaryDirectory(dir=ROOT) as home, patch.dict(os.environ, {'HERMES_HOME':home}):
            profile = get_provider_profile('gemini-login')
            self.assertIs(profile, package.gemini_login)
            for alias in ('google-gemini-cli','gemini-oauth'):
                self.assertIs(get_provider_profile(alias), profile)
        self.assertEqual(profile.auth_type, 'external_process')
        self.assertEqual(profile.process_command, '/Applications/Gemini.app/Contents/Helpers/agy')
        self.assertFalse(profile.base_url.startswith('acp://'))
        self.assertEqual(profile.process_args, ())
        self.assertEqual(set(profile.fallback_models), {'gemini-4-argon','gemini-3.8-flash'})
        self.assertFalse(profile.supports_vision)
        self.assertFalse(profile.supports_vision_tool_messages)
        self.assertFalse(profile.supports_model_listing)
        for model in profile.fallback_models:
            self.assertEqual(profile.model_capabilities[model]['modalities'], {'input':['text'],'output':['text']})
            self.assertTrue(profile.model_capabilities[model]['tool_call'])
        self.assertTrue((ROOT / 'provider/plugin.yaml').exists())

    def test_openai_client_preserves_host_calls_and_usage(self):
        package = provider()
        client = package.gemini_login.create_client(command=str(ROOT/'tests/fixture_cli.py'), bridge_path=str(ROOT/'gemini_login_bridge.py'), timeout=10, api_key='not-used', unknown_future_kwarg=True)
        self.assertIsNotNone(client, 'provider client not implemented')
        req = {'model':'gemini-3.8-flash','messages':[{'role':'user','content':'lookup 雪'}], 'tools':[{'type':'function','function':{'name':'lookup','parameters':{'type':'object'}}}], 'reasoning_effort':'high', 'max_tokens':100}
        with patch.dict(os.environ, {'BRIDGE_FIXTURE_MODE':'host_tool'}):
            result = client.chat.completions.create(**req)
        self.assertEqual(result.model, 'gemini-3.8-flash')
        self.assertEqual(result.choices[0].finish_reason, 'tool_calls')
        call = result.choices[0].message.tool_calls[0]
        self.assertEqual(call.function.name, 'lookup')
        self.assertEqual(call.function.arguments, '{"word":"雪"}')
        self.assertEqual(result.usage.prompt_tokens, 2324)
        self.assertEqual(result.usage.prompt_tokens_details.cached_tokens, 0)
        self.assertEqual(result.raw_usage['thinking_tokens'], 505)
        req['messages'] += [{'role':'assistant','content':None,'tool_calls':[{'id':'h1','type':'function','function':{'name':'lookup','arguments':'{}'}}]}, {'role':'tool','tool_call_id':'h1','content':'雪 café'}]
        with patch.dict(os.environ, {'BRIDGE_FIXTURE_MODE':'replay'}):
            answer = client.chat.completions.create(**req)
        self.assertEqual(answer.choices[0].message.content, 'BRIDGE_OK')
        self.assertEqual(answer.choices[0].finish_reason, 'stop')
        client.close()

    def test_maximum_host_reasoning_uses_supported_native_high(self):
        profile=provider().gemini_login
        for requested, expected in [('none','low'),('minimal','low'),('low','low'),('medium','medium'),('high','high'),('xhigh','high'),('max','high'),('ultra','high')]:
            with self.subTest(requested=requested):
                self.assertEqual(profile.build_api_kwargs_extras(reasoning_config={'effort':requested})[1],{'reasoning_effort':expected})
        with self.assertRaises(ValueError):
            profile.build_api_kwargs_extras(reasoning_config={'effort':'invalid'})

    def test_stream_shape_and_reasoning_hook(self):
        package = provider()
        extras, top = package.gemini_login.build_api_kwargs_extras(reasoning_config={'effort':'low'})
        self.assertEqual(top, {'reasoning_effort':'low'}, 'configured effort must reach native model')
        client = package.gemini_login.create_client(command=str(ROOT/'tests/fixture_cli.py'), bridge_path=str(ROOT/'gemini_login_bridge.py'), timeout=10)
        req = {'model':'gemini-3.8-flash','messages':[{'role':'user','content':'lookup'}], 'tools':[{'type':'function','function':{'name':'lookup','parameters':{'type':'object'}}}], 'stream':True}
        with patch.dict(os.environ, {'BRIDGE_FIXTURE_MODE':'host_tool'}):
            chunks = client.chat.completions.create(**req)
        self.assertIsInstance(chunks, list)
        self.assertEqual(chunks[0].choices[0].delta.tool_calls[0].function.name, 'lookup')
        self.assertEqual(chunks[0].choices[0].delta.tool_calls[0].index, 0)
        self.assertEqual(chunks[0].choices[0].finish_reason, 'tool_calls')
        self.assertEqual(chunks[-1].choices, [])
        self.assertEqual(chunks[-1].usage.prompt_tokens_details.cached_tokens, 0)
        self.assertTrue(chunks.conversation_id)
        self.assertEqual(chunks.raw_usage['input_tokens'], 2324)
        client.close()

    def test_client_cancel_and_host_interrupt_stop_inference(self):
        from tools.interrupt import set_interrupt
        package = provider()
        probe = package.gemini_login.create_client()
        self.assertTrue(hasattr(probe, 'cancel'), 'client cancellation not implemented')
        probe.close()
        for action in ('cancel', 'close', 'host_interrupt'):
            client = package.gemini_login.create_client(command=str(ROOT/'tests/fixture_cli.py'), bridge_path=str(ROOT/'gemini_login_bridge.py'), timeout=3)
            with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                pidfile = pathlib.Path(directory) / 'pids.json'
                outcomes = []
                def call():
                    try:
                        outcomes.append(client.chat.completions.create(model='gemini-3.8-flash', messages=[{'role':'user','content':'wait'}]))
                    except Exception as exc:
                        outcomes.append(exc)
                with patch.dict(os.environ, {'BRIDGE_FIXTURE_MODE':'sleep', 'BRIDGE_FIXTURE_PIDS':str(pidfile), 'GEMINI_LOGIN_PARENT_PROCESS_GROUP':'1'}):
                    worker = threading.Thread(target=call, daemon=True)
                    worker.start()
                    try:
                        deadline = time.monotonic()+2
                        while not pidfile.exists() and time.monotonic()<deadline:
                            time.sleep(0.02)
                        self.assertTrue(pidfile.exists())
                        pids = json.loads(pidfile.read_text())
                        self.assertNotEqual(os.getpgid(pids[0]), os.getpgrp(), 'imported Hermes bridge must own a separate group even when Pi env flag is present')
                        if action == 'host_interrupt':
                            set_interrupt(True, worker.ident)
                        else:
                            getattr(client, action)()
                        worker.join(timeout=2)
                        self.assertFalse(worker.is_alive())
                        self.assertIsInstance(outcomes[0], ValueError)
                        for pid in pids:
                            state = subprocess.run(['ps','-o','stat=','-p',str(pid)], capture_output=True,text=True).stdout.strip()
                            self.assertTrue(not state or state.startswith('Z'))
                    finally:
                        set_interrupt(False, worker.ident)
                        client.close()
                        if pidfile.exists():
                            try:
                                os.killpg(json.loads(pidfile.read_text())[0], signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                        worker.join(timeout=3)
            client.close()
            with self.assertRaises(RuntimeError):
                client.chat.completions.create(model='gemini-3.8-flash', messages=[{'role':'user','content':'closed'}])

    def test_isolated_plugin_discovery_resolves_native_command(self):
        from providers import get_provider_profile, provider_source
        from hermes_cli.auth import resolve_external_process_provider_credentials
        from agent.agent_runtime_helpers import _provider_supplied_client
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory(dir=ROOT) as home:
            target = pathlib.Path(home)/'plugins/model-providers/gemini-login'
            target.parent.mkdir(parents=True)
            target.symlink_to(ROOT/'provider', target_is_directory=True)
            with patch.dict(os.environ, {'HERMES_HOME':home}):
                profile = get_provider_profile('google-gemini-cli')
                self.assertEqual(profile.name, 'gemini-login')
                self.assertEqual(provider_source('gemini-login'), 'user')
                creds = resolve_external_process_provider_credentials('gemini-login')
                self.assertEqual(creds['command'], '/Applications/Gemini.app/Contents/Helpers/agy')
                self.assertEqual(creds['args'], [])
                self.assertEqual(creds['base_url'], 'gemini-login://antigravity')
                client = _provider_supplied_client(SimpleNamespace(provider='gemini-login'), {**creds,'bridge_path':str(ROOT/'gemini_login_bridge.py')})
                self.assertIsNotNone(client)
                self.assertTrue(callable(client.chat.completions.create))
                client.close()


if __name__ == '__main__':
    unittest.main()
