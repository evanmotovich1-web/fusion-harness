"""Offline bridge contract tests. jev-test is a fixture model, never live proof."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = Path.home() / "code/sssf/adws/adw_modules/jev.py"
spec = importlib.util.spec_from_file_location("jev_bridge_under_test", ROOT / "jev_bridge.py")
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)


def answer(options, selected, confidence=0.8):
    rest = (1 - confidence) / (len(options) - 1)
    return {"type": "choice", "choice": selected, "confidence": confidence,
            "probabilities": {name: confidence if name == selected else rest for name in options}}


class JevBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.envfile = self.root / "fixture.env"
        self.envfile.write_text("TYPESAFE_API_KEY=fixture-private-key\n")
        self.key = "fixture-private-key"
        self.envpatch = patch.dict(os.environ, {
            "HOME": str(self.root), "OPENCODE_ADW_JEV_CLIENT": str(CANONICAL),
            "OPENCODE_ADW_JEV_ENV_FILE": str(self.envfile),
        }, clear=True)
        self.envpatch.start()
        self.addCleanup(self.envpatch.stop)
        # No test can accidentally infer over HTTP, including canonical-client tests.
        self.network = patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network forbidden"))
        self.network_mock = self.network.start()
        self.addCleanup(self.network.stop)
        self.client = bridge._load_client()
        data = patch.object(self.client, "DATA_DIR", self.root / "client-data")
        data.start()
        self.addCleanup(data.stop)
        self.real_ask = self.client.ask
        ask = patch.object(self.client, "ask", side_effect=self.fake_ask)
        self.ask = ask.start()
        self.addCleanup(ask.stop)
        self.next_action = None
        self.focus = "correctness"
        self.focus_confidence = 0.8
        self.confidence = 0.8
        self.change = lambda result: None

    def tearDown(self):
        self.network_mock.assert_not_called()

    def fake_ask(self, state, questions, *, run, label, budget_s):
        self.assertEqual(os.environ["TYPESAFE_API_KEY"], self.key)
        self.assertLessEqual(budget_s, 30)
        folder = Path(run.session_dir) / "jev"
        self.assertTrue(folder.is_dir())
        receipt = self.client._receipt(run, label, {"fixture": True})
        selected = self.next_action or ("build" if state["phase"] == "focus" else "repair")
        result = self.client.JevResult(
            answers={"next_action": answer(questions["next_action"]["criteria"], selected, self.confidence),
                     "focus": answer(questions["focus"]["criteria"], self.focus, self.focus_confidence)},
            model_requested="jev-latest", model_resolved="jev-test", attempts=1,
            elapsed_ms=12.5, input_tokens=123, output_tokens=17,
            cost_usd=0, cost_source="fixture", receipt_path=receipt)
        self.change(result)
        return result

    def decide(self, phase="decision", **kwargs):
        return bridge.decide({"phase": phase, "summary": "bounded evidence"},
                             receipt_dir=self.root / "run/jev", label="unit", **kwargs)

    def test_status_metadata_no_inference_and_no_env_injection(self):
        self.assertEqual(bridge.status(), {"configured": True, "model": "jev-latest", "reason": None})
        self.ask.assert_not_called()
        self.assertNotIn("TYPESAFE_API_KEY", os.environ)

    def test_canonical_dataclass_module_registered(self):
        self.assertIs(sys.modules[self.client.__name__], self.client)
        self.assertEqual(self.client.JevResult.__module__, self.client.__name__)

    def test_env_key_precedence_preserved(self):
        self.key = "existing-private-key"
        os.environ["TYPESAFE_API_KEY"] = self.key
        self.envfile.unlink()
        self.assertTrue(bridge.status()["configured"])
        self.decide()
        self.assertEqual(os.environ["TYPESAFE_API_KEY"], self.key)

    def test_empty_existing_key_not_overwritten(self):
        os.environ["TYPESAFE_API_KEY"] = ""
        self.assertEqual(bridge.status()["reason"], "no_key")
        with self.assertRaisesRegex(bridge.JevError, "^no_key$"):
            self.decide()
        self.assertEqual(os.environ["TYPESAFE_API_KEY"], "")
        self.ask.assert_not_called()

    def test_missing_key(self):
        self.envfile.unlink()
        self.assertFalse(bridge.status()["configured"])
        with self.assertRaisesRegex(bridge.JevError, "^no_key$"):
            self.decide()

    def test_literal_dotenv_forms_only_named_key(self):
        for text in ("TYPESAFE_API_KEY=fixture-private-key # comment\n",
                     " export TYPESAFE_API_KEY = 'fixture-private-key' # comment\n",
                     'TYPESAFE_API_KEY="fixture-private-key"\n'):
            with self.subTest(text=text):
                self.envfile.write_text("UNRELATED=never-inject\n" + text)
                self.assertTrue(bridge.status()["configured"])
                self.decide()
                self.assertNotIn("UNRELATED", os.environ)
                self.assertNotIn("TYPESAFE_API_KEY", os.environ)

    def test_default_fallback_path_is_existing_sssf_env(self):
        os.environ.pop("OPENCODE_ADW_JEV_ENV_FILE")
        fallback = self.root / "code/sssf/.env"
        fallback.parent.mkdir(parents=True)
        fallback.write_text("TYPESAFE_API_KEY=fixture-private-key\n")
        self.assertTrue(bridge.status()["configured"])
        self.decide()
        self.assertEqual(fallback.read_text(), "TYPESAFE_API_KEY=fixture-private-key\n")

    def test_dotenv_never_executes_interpolates_or_accepts_malformed(self):
        marker = self.root / "executed"
        values = [f"$(touch {marker})", f"`touch {marker}`", '"${OTHER}"',
                  "'literal\\nescape'", "'unterminated", "", "two words", "safe;command"]
        for value in values:
            with self.subTest(value=value):
                self.envfile.write_text(f"TYPESAFE_API_KEY={value}\n")
                self.assertEqual(bridge.status()["reason"], "no_key")
        self.assertFalse(marker.exists())
        self.ask.assert_not_called()

    def test_disabled_env_and_kill_file(self):
        os.environ["JEV_DISABLED"] = "true"
        self.assertEqual(bridge.status()["reason"], "disabled")
        with self.assertRaisesRegex(bridge.JevError, "^disabled$"):
            self.decide()
        os.environ.pop("JEV_DISABLED")
        self.client.DATA_DIR.mkdir()
        (self.client.DATA_DIR / "JEV_DISABLED").touch()
        self.assertFalse(bridge.status()["configured"])
        self.ask.assert_not_called()

    def test_only_typesafe_backend(self):
        for backend in ("mock", "fixture", "unknown"):
            with self.subTest(backend=backend):
                os.environ["JEV_BACKEND"] = backend
                self.assertEqual(bridge.status()["reason"], "invalid_backend")
                with self.assertRaisesRegex(bridge.JevError, "^invalid_backend$"):
                    self.decide()
        self.ask.assert_not_called()

    def test_missing_syntax_and_invalid_client_are_not_configured(self):
        for code in (None, "def broken(:\n", "MODEL='jev-latest'\n"):
            with self.subTest(code=code):
                path = self.root / "override.py"
                if code is not None:
                    path.write_text(code)
                os.environ["OPENCODE_ADW_JEV_CLIENT"] = str(path)
                self.assertFalse(bridge.status()["configured"])
                with self.assertRaises(bridge.JevError):
                    self.decide()

    def test_invalid_ask_signature_rejected(self):
        self.ask.side_effect = None
        # Force loader validation of a new import rather than its validated cache.
        path = self.root / "client.py"
        path.write_text("from dataclasses import dataclass\nMODEL='jev-latest'\n"
                        "@dataclass\nclass JevResult:\n"
                        " answers: dict\n model_requested: str\n model_resolved: str\n"
                        " input_tokens: int\n output_tokens: int\n elapsed_ms: float\n receipt_path: str\n"
                        "def disabled(): return False\ndef ask(): pass\n")
        os.environ["OPENCODE_ADW_JEV_CLIENT"] = str(path)
        self.assertFalse(bridge.status()["configured"])

    def test_focus_phase_asks_action_and_separate_focus(self):
        result = self.decide("focus")
        self.assertEqual(result["recommendation"], "build")
        self.assertEqual(result["focus"], "correctness")
        questions = self.ask.call_args.args[1]
        self.assertEqual(set(questions["next_action"]["criteria"]), {"build", "stop", "other"})
        self.assertEqual(set(questions["focus"]["criteria"]), set(bridge._FOCI))

    def test_decision_phase_metadata_receipt_and_private_state_hash(self):
        result = self.decide()
        required = {"recommendation", "focus", "confidence", "probabilities", "model_requested",
                    "model_resolved", "input_tokens", "output_tokens", "elapsed_ms", "receipt_path"}
        self.assertTrue(required <= set(result))
        self.assertEqual(result["model_resolved"], "jev-test")
        self.assertEqual((result["input_tokens"], result["output_tokens"]), (123, 17))
        path = Path(result["receipt_path"])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        data = json.loads(path.read_text())
        self.assertEqual(data["confidence_floor"], 0.5)
        self.assertEqual(data["confidence_policy"], "provisional")
        self.assertEqual(data["state_sha256"], hashlib.sha256(json.dumps(
            {"phase": "decision", "summary": "bounded evidence"}, sort_keys=True).encode()).hexdigest())
        self.assertTrue(Path(data["client_receipt_path"]).is_file())
        self.assertNotIn("bounded evidence", path.read_text())
        self.assertNotIn(self.key, json.dumps(result) + path.read_text() + json.dumps(bridge.status()))
        self.assertNotIn("TYPESAFE_API_KEY", os.environ)
        self.assertEqual(set(self.ask.call_args.args[1]["next_action"]["criteria"]),
                         {"finish", "repair", "stop", "other"})

    def test_finish_hint_on_failed_checks_has_no_approval_authority(self):
        self.next_action = "finish"
        self.focus_confidence = 0.25
        self.focus = "other"
        result = bridge.decide({"phase": "decision", "checks": "FAILED", "reviewer": "FAIL"},
                               receipt_dir=self.root / "run/jev", label="finish_hint")
        self.assertEqual(result["recommendation"], "finish")
        self.assertEqual(result["focus"], "general")
        self.assertNotIn("approved", result)
        self.assertEqual(result["focus_confidence"], 0.25)

    def test_stop_ignores_unused_focus_confidence(self):
        self.next_action, self.focus, self.focus_confidence = "stop", "other", 0.25
        self.assertEqual(self.decide()["recommendation"], "stop")

    def test_uncertain_repair_focus_is_general_without_fake_confidence(self):
        self.focus, self.focus_confidence = "other", 0.25
        result = self.decide()
        self.assertEqual(result["focus"], "general")
        self.assertEqual(result["focus_confidence"], 0.25)

    def test_uncertain_build_focus_is_general_without_aborting(self):
        for focus, confidence in (("other", 0.25), ("other", 0.8), ("correctness", 0.25)):
            with self.subTest(focus=focus, confidence=confidence):
                self.focus, self.focus_confidence = focus, confidence
                # Confidence is independent of the distribution's chosen probability.
                def change(result):
                    result.answers["focus"] = answer(bridge._FOCI, focus, 0.8)
                    result.answers["focus"]["confidence"] = confidence
                self.change = change
                result = self.decide("focus")
                self.assertEqual(result["recommendation"], "build")
                self.assertEqual(result["focus"], "general")
                self.assertEqual(result["focus_confidence"], confidence)
                self.assertEqual(result["original_focus"], focus)
                self.assertEqual(result["route"], "advice")

    def test_confidence_is_independent_of_chosen_probability(self):
        def change(result):
            result.answers["next_action"] = answer(("finish", "repair", "stop", "other"), "repair", 0.88)
            result.answers["next_action"]["confidence"] = 0.81
        self.change = change
        result = self.decide()
        self.assertEqual(result["recommendation"], "repair")
        self.assertEqual(result["confidence"], 0.81)
        self.assertEqual(result["probabilities"]["repair"], 0.88)

    def test_independent_low_action_confidence_routes_consult(self):
        self.change = lambda r: r.answers["next_action"].update(confidence=0.49)
        result = self.decide()
        self.assertEqual(result["recommendation"], "repair")
        self.assertEqual(result["confidence"], 0.49)
        self.assertEqual(result["route"], "consult")
        self.assertTrue(result["uncertain"])

    def test_action_floor_and_other_route_consult(self):
        self.confidence = 0.4
        self.assertEqual(self.decide()["route"], "consult")
        self.confidence, self.next_action = 0.8, "other"
        result = self.decide()
        self.assertEqual(result["recommendation"], "other")
        self.assertEqual(result["confidence"], 0.8)
        self.assertEqual(result["route"], "consult")
        self.assertTrue(result["uncertain"])
        self.confidence, self.next_action = 0.5, "repair"
        result = self.decide()
        self.assertEqual(result["confidence"], 0.5)
        self.assertEqual(result["confidence_floor"], 0.5)
        self.assertEqual(result["route"], "advice")
        self.assertFalse(result["uncertain"])

    def test_actual_stop_low_confidence_preserved_and_consult_receipted(self):
        def change(result):
            result.answers["next_action"] = {
                "type": "choice", "choice": "stop", "confidence": 0.28,
                "probabilities": {"build": 0.30, "stop": 0.52, "other": 0.18},
            }
            result.answers["focus"] = answer(bridge._FOCI, "correctness", 0.8)
            result.answers["focus"]["confidence"] = 0.73
        self.change = change
        result = self.decide("focus")
        self.assertEqual(result["recommendation"], "stop")
        self.assertEqual(result["confidence"], 0.28)
        self.assertEqual(result["probabilities"], {"build": 0.30, "stop": 0.52, "other": 0.18})
        self.assertEqual(result["route"], "consult")
        self.assertTrue(result["uncertain"])
        self.assertEqual(result["confidence_floor"], 0.5)
        self.assertEqual(result["original_focus"], "correctness")
        self.assertEqual(result["focus_confidence"], 0.73)
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        for name in ("recommendation", "confidence", "probabilities", "route", "uncertain",
                     "confidence_floor", "original_focus", "focus_confidence", "focus_probabilities"):
            self.assertEqual(receipt[name], result[name])

    def test_low_confidence_finish_routes_consult_not_advice(self):
        self.next_action = "finish"
        self.change = lambda r: r.answers["next_action"].update(confidence=0.28)
        result = self.decide()
        self.assertEqual(result["recommendation"], "finish")
        self.assertEqual(result["confidence"], 0.28)
        self.assertEqual(result["route"], "consult")
        self.assertTrue(result["uncertain"])

    def test_high_confidence_stop_is_advice(self):
        self.next_action = "stop"
        result = self.decide()
        self.assertEqual(result["recommendation"], "stop")
        self.assertEqual(result["route"], "advice")
        self.assertFalse(result["uncertain"])

    def test_malformed_low_confidence_is_rejected_before_routing(self):
        def change(result):
            result.answers["next_action"]["confidence"] = 0.28
            result.answers["next_action"]["probabilities"]["repair"] = float("nan")
        self.change = change
        with self.assertRaisesRegex(bridge.JevError, "^invalid_response$"):
            self.decide()

    def test_malformed_actual_typed_answers(self):
        mutations = [
            lambda a: a.update(type="score"),
            lambda a: a.update(choice="undeclared"),
            lambda a: a.update(confidence=1.1),
            lambda a: a.update(confidence=True),
            lambda a: a.update(confidence=float("nan")),
            lambda a: a["probabilities"].update(repair=float("inf")),
            lambda a: a["probabilities"].update(repair=-0.1),
            lambda a: a["probabilities"].update(repair=1.1),
            lambda a: a["probabilities"].update(extra=0),
            lambda a: a["probabilities"].pop("other"),
            lambda a: a["probabilities"].update(repair=0.6),
            lambda a: a.update(choice="stop", confidence=a["probabilities"]["stop"]),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                self.change = lambda r: mutate(r.answers["next_action"])
                with self.assertRaisesRegex(bridge.JevError, "^invalid_response$"):
                    self.decide()
                self.assertNotIn("TYPESAFE_API_KEY", os.environ)

    def test_malformed_focus_still_rejected_when_unused(self):
        self.next_action = "finish"
        self.change = lambda r: r.answers["focus"].update(confidence=float("nan"))
        with self.assertRaisesRegex(bridge.JevError, "^invalid_response$"):
            self.decide()

    def test_non_jev_mock_fixture_models_refused(self):
        for model in ("mock-jev", "fixture", "jev-fixture", "jev-mock", "other-model", "jev\n"):
            with self.subTest(model=model):
                self.change = lambda r: setattr(r, "model_resolved", model)
                with self.assertRaisesRegex(bridge.JevError, "^invalid_response$"):
                    self.decide()

    def test_production_jev_alias_resolution_allowed(self):
        self.change = lambda r: setattr(r, "model_resolved", "jev1.13")
        self.assertEqual(self.decide()["model_resolved"], "jev1.13")

    def test_invalid_usage_and_model_requested(self):
        for name, value in (("input_tokens", -1), ("output_tokens", True),
                            ("elapsed_ms", float("inf")), ("elapsed_ms", -1),
                            ("model_requested", "invented"), ("answers", {})):
            with self.subTest(field=name):
                self.change = lambda r: setattr(r, name, value)
                with self.assertRaisesRegex(bridge.JevError, "^invalid_response$"):
                    self.decide()

    def test_no_untyped_result(self):
        self.ask.side_effect = lambda *a, **kw: {"recommendation": "finish"}
        with self.assertRaisesRegex(bridge.JevError, "^invalid_response$"):
            self.decide()

    def test_client_error_whitelist_and_env_restoration(self):
        for reason, expected in (("refused_input", "refused_input"), ("timeout", "timeout"),
                                 ("http_401", "http_401"), (self.key, "unavailable")):
            with self.subTest(expected=expected):
                self.ask.side_effect = self.client.JevUnavailable(reason)
                with self.assertRaises(bridge.JevError) as caught:
                    self.decide()
                self.assertEqual(caught.exception.reason, expected)
                self.assertNotIn(self.key, str(caught.exception))
                self.assertNotIn("TYPESAFE_API_KEY", os.environ)
        self.ask.side_effect = RuntimeError(self.key)
        os.environ["TYPESAFE_API_KEY"] = self.key
        with self.assertRaisesRegex(bridge.JevError, "^unavailable$"):
            self.decide()
        self.assertEqual(os.environ["TYPESAFE_API_KEY"], self.key)

    def test_canonical_sanitizer_refuses_secret_before_transport(self):
        self.ask.side_effect = self.real_ask
        with patch.object(self.client, "_transport") as transport:
            with self.assertRaisesRegex(bridge.JevError, "^refused_input$"):
                bridge.decide({"phase": "decision", "summary": self.key},
                              receipt_dir=self.root / "run/jev", label="secret")
            transport.assert_not_called()
        for path in (self.root / "run/jev").glob("*.json"):
            self.assertNotIn(self.key, path.read_text())
        self.assertNotIn("TYPESAFE_API_KEY", os.environ)

    def test_canonical_success_with_transport_patched_no_network(self):
        self.ask.side_effect = self.real_ask

        def transport(body, key, deadline, progress):
            self.assertEqual(key, self.key)
            request = json.loads(body)
            progress[0] = 1
            return {"model": "jev1.13", "answers": {
                "next_action": answer(request["questions"]["next_action"]["criteria"], "repair"),
                "focus": answer(request["questions"]["focus"]["criteria"], "edge_cases"),
            }, "usage": {"input_tokens": 201, "output_tokens": 32}}

        with patch.object(self.client, "_transport", side_effect=transport) as mocked:
            result = self.decide(budget_s=30)
        mocked.assert_called_once()
        self.assertEqual(result["model_resolved"], "jev1.13")
        self.assertEqual(result["focus"], "edge_cases")
        self.assertEqual(result["input_tokens"], 201)
        adapter = json.loads(Path(result["receipt_path"]).read_text())
        canonical = json.loads(Path(adapter["client_receipt_path"]).read_text())
        self.assertEqual(canonical["status"], "ok")
        self.assertEqual(set(canonical["questions"]), {"next_action", "focus"})
        for receipt in (adapter, canonical):
            self.assertIn("state_sha256", receipt)
            self.assertNotIn("bounded evidence", json.dumps(receipt))
            self.assertNotIn(self.key, json.dumps(receipt))
        self.assertNotIn("TYPESAFE_API_KEY", os.environ)

    def test_secret_in_result_metadata_is_not_returned_or_persisted(self):
        self.key = "private-unit-key"
        self.envfile.write_text(f"TYPESAFE_API_KEY={self.key}\n")
        self.change = lambda r: setattr(r, "model_resolved", "jev-" + self.key)
        with self.assertRaisesRegex(bridge.JevError, "^invalid_response$"):
            self.decide()
        self.assertFalse(list((self.root / "run/jev").glob("adapter_*.json")))
        self.assertNotIn(self.key, json.dumps(bridge.status()))

    def test_adapter_never_persists_raw_state_even_with_stubbed_sanitizer(self):
        result = bridge.decide({"phase": "decision", "summary": self.key},
                               receipt_dir=self.root / "run/jev", label="private")
        self.assertNotIn(self.key, Path(result["receipt_path"]).read_text())

    def test_client_receipt_required_inside_requested_directory(self):
        for value in (None, "relative.json", str(self.root / "missing.json")):
            with self.subTest(path=value):
                self.change = lambda r: setattr(r, "receipt_path", value)
                with self.assertRaisesRegex(bridge.JevError, "^invalid_response$"):
                    self.decide()

    def test_adapter_receipt_write_failure_restores_env(self):
        with patch.object(bridge, "_private_receipt", side_effect=OSError(self.key)):
            with self.assertRaises(bridge.JevError) as caught:
                self.decide()
        self.assertNotIn(self.key, str(caught.exception))
        self.assertNotIn("TYPESAFE_API_KEY", os.environ)

    def test_inputs_budget_labels_and_absolute_jev_folder(self):
        for kwargs in ({"budget_s": 31}, {"budget_s": 0}, {"budget_s": float("nan")},
                       {"budget_s": True}, {"label": "../bad"}, {"receipt_dir": "relative/jev"},
                       {"receipt_dir": self.root / "not-jev"}):
            with self.subTest(kwargs=kwargs):
                options = dict(receipt_dir=self.root / "run/jev", label="unit", **{})
                options.update(kwargs)
                with self.assertRaisesRegex(bridge.JevError, "^refused_input$"):
                    bridge.decide({"phase": "decision"}, **options)
        for state in ({}, {"phase": "unknown"}, [], {"phase": "focus", "bad": float("nan")}):
            with self.subTest(state=state):
                with self.assertRaisesRegex(bridge.JevError, "^refused_input$"):
                    bridge.decide(state, receipt_dir=self.root / "run/jev", label="unit")
        self.ask.assert_not_called()

    def test_symlink_receipt_directory_refused(self):
        destination = self.root / "destination"
        destination.mkdir()
        folder = self.root / "jev"
        folder.symlink_to(destination, target_is_directory=True)
        with self.assertRaisesRegex(bridge.JevError, "^receipt_error$"):
            bridge.decide({"phase": "focus"}, receipt_dir=folder, label="unit")
        self.ask.assert_not_called()

    def select_repository(self):
        return bridge.select_repository("improve the scheduler", [dict(
            id="project_one", name="scheduler", description="Appointment calendars", aliases=["calendar"])],
            receipt_dir=self.root / "run/jev")

    def route_ask(self, state, questions, *, run, label, budget_s):
        self.assertEqual(set(questions), {"repository"})
        self.assertEqual(set(questions["repository"]["criteria"]), {"project_one", "other"})
        self.assertNotIn(str(self.root), json.dumps(state))
        result = self.client.JevResult(
            answers={"repository": answer(questions["repository"]["criteria"], "project_one", .88)},
            model_requested="jev-latest", model_resolved="jev-test", attempts=1,
            elapsed_ms=12.5, input_tokens=123, output_tokens=17, cost_usd=0,
            cost_source="fixture", receipt_path=self.client._receipt(run, label, {"fixture": True}))
        result.answers["repository"]["confidence"] = .81
        self.change(result)
        return result

    def test_repository_choice_independent_confidence_and_private_receipt(self):
        self.ask.side_effect = self.route_ask
        result = self.select_repository()
        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["selected_id"], "project_one")
        self.assertEqual(result["confidence"], .81)
        self.assertEqual(result["probabilities"]["project_one"], .88)
        self.assertEqual((result["input_tokens"], result["output_tokens"]), (123, 17))
        receipt = Path(result["receipt_path"])
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
        data = json.loads(receipt.read_text())
        self.assertEqual(data["raw_choice"], "project_one")
        self.assertEqual(data["confidence_floor"], .6)
        self.assertNotIn("improve the scheduler", receipt.read_text())
        self.assertNotIn(self.key, receipt.read_text())
        self.assertNotIn("TYPESAFE_API_KEY", os.environ)

    def test_repository_floor_other_and_raw_choice_preserved(self):
        self.ask.side_effect = self.route_ask
        for choice, confidence, status in (("project_one", .59, "needs_clarification"),
                                            ("project_one", .6, "selected"),
                                            ("other", .9, "needs_clarification")):
            with self.subTest(choice=choice, confidence=confidence):
                def change(result):
                    result.answers["repository"] = answer(("project_one", "other"), choice, .9)
                    result.answers["repository"]["confidence"] = confidence
                self.change = change
                result = self.select_repository()
                self.assertEqual(result["status"], status)
                self.assertEqual(result["raw_choice"], choice)
                self.assertEqual(result["selected_id"], choice if status == "selected" else None)

    def test_repository_rejects_unknown_or_malformed_typed_answers(self):
        self.ask.side_effect = self.route_ask
        mutations = [lambda a: a.update(choice="unknown"), lambda a: a.update(type="score"),
                     lambda a: a.update(confidence=True), lambda a: a.update(confidence=float("nan")),
                     lambda a: a["probabilities"].update(project_one=float("inf")),
                     lambda a: a["probabilities"].pop("other"),
                     lambda a: a["probabilities"].update(extra=0)]
        for mutation in mutations:
            self.change = lambda r: mutation(r.answers["repository"])
            with self.assertRaisesRegex(bridge.JevError, "^invalid_response$"):
                self.select_repository()
            self.assertNotIn("TYPESAFE_API_KEY", os.environ)

    def test_repository_rejects_paths_extra_fields_and_duplicate_ids(self):
        base = dict(id="project_one", name="scheduler", description="Calendars", aliases=[])
        bad = [[], [dict(base, path="/private/repo")], [dict(base, name="/private/repo")],
               [dict(base, aliases=["/private/repo"])], [dict(base, id="other")], [base, base],
               [dict(base, description="x" * 401)], [base] * 13]
        for candidates in bad:
            with self.subTest(candidates=candidates):
                with self.assertRaisesRegex(bridge.JevError, "^refused_input$"):
                    bridge.select_repository("task", candidates, receipt_dir=self.root / "run/jev")
        self.ask.assert_not_called()

    def test_repository_uses_canonical_sanitizer_before_transport(self):
        self.ask.side_effect = self.real_ask
        with patch.object(self.client, "_transport") as transport:
            with self.assertRaisesRegex(bridge.JevError, "^refused_input$"):
                bridge.select_repository(self.key, [dict(id="project_one", name="safe",
                    description="Safe", aliases=[])], receipt_dir=self.root / "run/jev")
            transport.assert_not_called()

    def test_repository_canonical_transport_contract_offline(self):
        self.ask.side_effect = self.real_ask
        def transport(body, key, deadline, progress):
            request = json.loads(body)
            progress[0] = 1
            response = answer(request["questions"]["repository"]["criteria"], "project_one", .88)
            response["confidence"] = .81
            return {"model": "jev1.13", "answers": {"repository": response},
                    "usage": {"input_tokens": 201, "output_tokens": 32}}
        with patch.object(self.client, "_transport", side_effect=transport):
            result = self.select_repository()
        self.assertEqual(result["model_resolved"], "jev1.13")
        self.assertEqual(result["confidence"], .81)

    def test_repository_unavailable_restores_environment(self):
        self.ask.side_effect = self.client.JevUnavailable("timeout")
        with self.assertRaisesRegex(bridge.JevError, "^timeout$"):
            self.select_repository()
        self.assertNotIn("TYPESAFE_API_KEY", os.environ)

    def test_repository_result_receipt_and_usage_validated(self):
        self.ask.side_effect = self.route_ask
        for name, value in (("receipt_path", "relative.json"), ("input_tokens", True),
                            ("elapsed_ms", -1), ("model_resolved", "jev-mock")):
            self.change = lambda r: setattr(r, name, value)
            with self.assertRaisesRegex(bridge.JevError, "^invalid_response$"):
                self.select_repository()

    def test_concurrent_calls_and_status_share_temporary_key_lock(self):
        entered, release = threading.Event(), threading.Event()
        original = self.fake_ask

        def blocking(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(3))
            return original(*args, **kwargs)

        self.ask.side_effect = blocking
        with ThreadPoolExecutor(max_workers=3) as pool:
            first = pool.submit(self.decide)
            self.assertTrue(entered.wait(3))
            second = pool.submit(self.decide)
            probe = pool.submit(bridge.status)
            self.assertFalse(second.done())
            self.assertFalse(probe.done())
            release.set()
            self.assertEqual(first.result()["recommendation"], "repair")
            self.assertEqual(second.result()["recommendation"], "repair")
            self.assertTrue(probe.result()["configured"])
        self.assertNotIn("TYPESAFE_API_KEY", os.environ)


if __name__ == "__main__":
    unittest.main()
