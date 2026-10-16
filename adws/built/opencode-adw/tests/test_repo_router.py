"""Offline router tests: temporary Git metadata, fake discovery and inference."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import repo_router as router


class RepositoryRouterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve()
        self.workspace = self.home / "workspace"
        self.workspace.mkdir()
        self.env = patch.dict(os.environ, {"HOME": str(self.home)}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.repos = []
        self.discovery = patch.object(router, "_discover", side_effect=lambda w: {"repos": self.repos})
        self.discovery.start()
        self.addCleanup(self.discovery.stop)
        self.semantic = patch.object(router.jev_bridge, "select_repository",
                                     side_effect=router.jev_bridge.JevError("no_key"))
        self.select = self.semantic.start()
        self.addCleanup(self.semantic.stop)
        self.network = patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("no network"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def repo(self, name, purpose=""):
        path = self.home / name
        path.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)
        if purpose:
            (path / "README.md").write_text(purpose)
        self.repos.append(dict(path=str(path), name=path.name))
        return path

    def resolve(self, request="make the required change", **kwargs):
        return router.resolve(request, receipt_dir=self.home / "run/routing",
                              workspace_root=self.workspace, **kwargs)

    def test_exact_name_and_private_receipt_no_raw_task(self):
        path = self.repo("widget")
        result = self.resolve("fix widget")
        self.assertEqual((result["status"], result["method"], result["selected_repo"]),
                         ("resolved", "exact", str(path)))
        self.select.assert_not_called()
        receipt = Path(result["receipt_path"])
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
        data = json.loads(receipt.read_text())
        self.assertEqual(data["request_sha256"], hashlib.sha256(b"fix widget").hexdigest())
        self.assertNotIn("fix widget", receipt.read_text())
        self.assertEqual(data["candidates"][0]["canonical_checkout"], str(path))

    def test_native_context_nested_directory(self):
        path = self.repo("widget")
        child = path / "src"
        child.mkdir()
        self.assertEqual(self.resolve(context_directory=child)["selected_repo"], str(path))
        self.select.assert_not_called()

    def test_different_explicit_name_beats_context(self):
        first, second = self.repo("first"), self.repo("second")
        result = self.resolve("fix second", context_directory=first)
        self.assertEqual(result["selected_repo"], str(second))
        self.assertEqual(result["method"], "exact")

    def test_ambiguous_duplicate_name_no_semantic_guess(self):
        self.repo("a/widget")
        self.repo("b/widget")
        result = self.resolve("fix widget")
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(len(result["candidates"]), 2)
        self.select.assert_not_called()

    def test_full_path_disambiguates_duplicate_name(self):
        path = self.repo("a/widget")
        self.repo("b/widget")
        self.assertEqual(self.resolve("fix " + str(path))["selected_repo"], str(path))

    def test_multiple_named_projects_clarify(self):
        self.repo("first")
        self.repo("second")
        self.assertEqual(self.resolve("fix first and second")["method"], "ambiguous")
        self.select.assert_not_called()

    def test_no_cwd_inference_or_first_candidate_fallback(self):
        self.repo("widget")
        result = self.resolve()
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIsNone(result["selected_repo"])
        self.assertEqual(result["question"].count("?"), 1)
        self.select.assert_called_once()

    def test_empty_catalog_clarifies_without_inference(self):
        result = self.resolve()
        self.assertEqual(result["candidates"], [])
        self.assertIsNone(result["selected_repo"])
        self.select.assert_not_called()

    def test_manual_spaces_canonical_git_root_without_source_edits(self):
        path = self.repo("path with spaces")
        before = sorted(str(p.relative_to(path)) for p in path.rglob("*"))
        result = self.resolve(explicit_repo=path)
        self.assertEqual((result["selected_repo"], result["method"]), (str(path), "explicit"))
        self.assertNotIn("confidence", result)
        self.assertEqual(before, sorted(str(p.relative_to(path)) for p in path.rglob("*")))
        self.select.assert_not_called()

    def test_manual_subdirectory_canonicalizes_without_catalog_or_model(self):
        root = self.repo("widget with spaces")
        path = root / "src/nested"
        path.mkdir(parents=True)
        with patch.object(router, "_catalog", side_effect=AssertionError("no catalog")), \
             patch.object(router, "_workspace", side_effect=AssertionError("no workspace lookup")):
            result = self.resolve(explicit_repo=path)
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["selected_repo"], str(root))
        self.assertEqual(result["method"], "explicit")
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["requested_path"], str(path))
        self.assertEqual(receipt["resolved_git_root"], str(root))
        self.assertEqual(receipt["catalog_source"], "explicit_git_probe")
        self.select.assert_not_called()

    def test_manual_non_git_missing_path_and_file_refused(self):
        path = self.repo("widget") / "file.txt"
        path.write_text("not a directory")
        for invalid in (path, self.workspace, self.home / "missing"):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.resolve(explicit_repo=invalid)["status"], "needs_clarification")
        self.select.assert_not_called()

    def test_manual_git_timeout_is_bounded_and_unresolved(self):
        path = self.repo("widget")
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        git = bin_dir / "git"
        git.write_text("#!" + sys.executable + "\nimport time\ntime.sleep(10)\n")
        git.chmod(0o700)
        with patch.dict(os.environ, {"PATH": str(bin_dir)}):
            started = time.monotonic()
            result = self.resolve(explicit_repo=path)
        self.assertLess(time.monotonic() - started, 2)
        self.assertIsNone(result["selected_repo"])
        self.assertEqual(result["status"], "needs_clarification")

    def test_manual_subdirectory_symlink_cannot_bypass_retirement(self):
        root = self.repo("tradingview-mcp-jackson")
        child = root / "src"
        child.mkdir()
        alias = self.home / "apparently-active"
        alias.symlink_to(child, target_is_directory=True)
        result = self.resolve(explicit_repo=alias)
        self.assertIsNone(result["selected_repo"])
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["requested_path"], str(alias))
        self.assertEqual(receipt["resolved_git_root"], str(root))

    def test_manual_linked_worktree_subdirectory_preserves_actual_root(self):
        main = self.repo("widget")
        linked = self.worktree(main, "widget-linked")
        child = linked / "src"
        child.mkdir()
        result = self.resolve(explicit_repo=child)
        self.assertEqual(result["selected_repo"], str(linked))

    def test_auto_is_not_manual_path(self):
        path = self.repo("widget")
        self.assertEqual(self.resolve("fix widget", explicit_repo="auto")["selected_repo"], str(path))

    def test_retired_and_archived_excluded_even_manual(self):
        for name in ("tradingview-mcp-jackson", "archive/widget", "parked/widget", "retired/widget"):
            path = self.repo(name)
            with self.subTest(name=name):
                self.assertEqual(self.resolve(explicit_repo=path)["status"], "needs_clarification")
        self.assertEqual(self.resolve()["candidates"], [])

    def test_retired_name_must_not_route_to_active_context(self):
        path = self.repo("active")
        result = self.resolve("fix tradingview-mcp-jackson", context_directory=path)
        self.assertIsNone(result["selected_repo"])
        self.assertEqual(result["method"], "excluded")

    def worktree(self, main, name):
        # Real linked-worktree metadata, with an unborn branch: no commit required.
        target = self.home / name
        target.mkdir()
        metadata = main / ".git/worktrees" / name
        metadata.mkdir(parents=True)
        (metadata / "HEAD").write_text("ref: refs/heads/" + name + "\n")
        (metadata / "commondir").write_text("../..\n")
        (metadata / "gitdir").write_text(str(target / ".git") + "\n")
        (target / ".git").write_text("gitdir: " + str(metadata) + "\n")
        self.repos.append(dict(path=str(target), name=name, is_worktree=True))
        return target

    def test_many_worktrees_do_not_starve_late_semantic_project(self):
        main = self.repo("aaa-platform")
        for index in range(150):
            self.worktree(main, "aaa-branch-" + str(index))
        target = self.repo("zzz-sundial", "# Sundial\n\nSolar appointment scheduling and calendar reservations.")
        self.repos.sort(key=lambda r: r["path"])
        real_git = shutil.which("git")
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        calls = self.home / "git-calls.jsonl"
        wrapper = bin_dir / "git"
        # Each unnecessary Git call costs real time: the old two-calls/worktree
        # path cannot reach the late project within the six-second child budget.
        wrapper.write_text("#!" + sys.executable + "\nimport json,os,sys,time\n"
                           "with open(" + repr(str(calls)) + ", 'a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\n"
                           "time.sleep(.04)\nos.execv(" + repr(real_git) + ", [" + repr(real_git) + ", *sys.argv[1:]])\n")
        wrapper.chmod(0o700)
        def select(request, candidates, **kwargs):
            match = next(c for c in candidates if "Solar appointment scheduling" in c["description"])
            return dict(status="selected", selected_id=match["id"], confidence=.81,
                        probabilities={match["id"]: .88, "other": .12},
                        model_requested="jev-latest", model_resolved="jev-test", input_tokens=12,
                        output_tokens=3, elapsed_ms=4, receipt_path="fixture")
        self.select.side_effect = select
        with patch.dict(os.environ, {"PATH": str(bin_dir)}):
            started = time.monotonic()
            result = self.resolve("improve solar appointment scheduling")
        self.assertLess(time.monotonic() - started, 6)
        self.assertEqual(result["selected_repo"], str(target))
        recorded = [json.loads(line) for line in calls.read_text().splitlines()]
        self.assertLessEqual(len(recorded), 4)  # Unknown workspace + final root verification.
        self.assertEqual(sum(str(target) in argv for argv in recorded), 2)
        self.assertFalse(any(str(main) in argv or "aaa-branch-" in " ".join(argv) for argv in recorded))
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertTrue(receipt["catalog_status"]["complete"])
        self.assertEqual(receipt["catalog_status"]["projects"], 2)
        self.assertEqual(receipt["catalog_status"]["described_projects"], 2)

    def test_discovered_fast_metadata_groups_without_git_and_reads_purpose_once(self):
        main = self.repo("widget", "# Widget\n\nPublic widget purpose.")
        first = self.worktree(main, "widget-A")
        second = self.worktree(main, "widget-B")
        rows = router._catalog(self.repos, "", [])
        roots = [r for r in rows if r.get("acquisition") == "local_git_metadata" and not r["description"]]
        self.assertEqual({r["root"] for r in roots}, {str(main), str(first), str(second)})
        self.assertEqual({r["common"] for r in roots}, {str(main / ".git")})
        descriptions = [r for r in rows if r.get("description")]
        self.assertEqual(len(descriptions), 1)
        self.assertEqual(descriptions[0]["root"], str(main))
        groups = router._groups(rows, str(first), str(second))
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["selected_repo"], str(first))

    def test_final_git_validation_rejects_metadata_only_repository(self):
        path = self.repo("widget")
        (path / ".git/config").write_text("[malformed\n")
        rows = router._catalog(self.repos, "fix widget", [])
        self.assertTrue(any(r.get("acquisition") == "local_git_metadata" for r in rows))
        result = self.resolve("fix widget")
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIsNone(result["selected_repo"])
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["reason"], "invalid_git_root")

    def test_empty_dotgit_is_not_a_root(self):
        path = self.home / "empty-widget"
        (path / ".git").mkdir(parents=True)
        self.repos.append(dict(path=str(path)))
        rows = router._catalog(self.repos, "", [])
        self.assertEqual(router._groups(rows, None, None), [])
        result = self.resolve("fix empty-widget")
        self.assertIsNone(result["selected_repo"])
        self.select.assert_not_called()

    def test_gitfile_without_commondir_keeps_submodule_root(self):
        parent = self.repo("parent")
        child = self.repo("parent/module")
        metadata = parent / ".git/modules/module"
        metadata.parent.mkdir(parents=True)
        shutil.move(str(child / ".git"), str(metadata))
        (child / ".git").write_text("gitdir: " + str(metadata) + "\n")
        rows = router._catalog([dict(path=str(child))], "", [])
        row = next(r for r in rows if r.get("root") == str(child))
        self.assertEqual(row["acquisition"], "local_git_metadata")
        self.assertEqual(row["canonical"], str(child))
        self.assertEqual(self.resolve("fix " + str(child))["selected_repo"], str(child))

    def test_catalog_order_prioritizes_context_explicit_and_main_checkouts(self):
        repos = [dict(path="/a/worktree", is_worktree=True), dict(path="/z/main"),
                 dict(path="/b/target", is_worktree=True)]
        with patch.object(router, "_events", return_value=[]) as events:
            router._catalog(repos, "fix target", ["/native/context"])
        payload = events.call_args.args[1]
        self.assertEqual(payload["paths"], ["/native/context", "/b/target", "/z/main", "/a/worktree"])
        self.assertEqual(set(payload["discovered_roots"]), {r["path"] for r in repos})

    def test_partial_catalog_budget_is_recorded(self):
        values = []
        router._catalog_rows(dict(paths=["/not-read"], discovered_roots=[]), values.append, budget_s=0)
        self.assertEqual(values, [dict(event="catalog_status", complete=False,
                                      examined_paths=0, projects=0, described_projects=0)])

    def test_worktrees_collapse_and_active_preferred(self):
        main = self.repo("widget")
        linked = self.worktree(main, "widget-feature")
        result = self.resolve("fix widget", context_directory=linked)
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["selected_repo"], str(linked))
        self.assertEqual(result["candidates"][0]["canonical_checkout"], str(main))

    def test_linked_only_catalog_uses_canonical_checkout(self):
        main = self.repo("widget")
        self.worktree(main, "widget-feature")
        self.repos.pop(0)
        self.assertEqual(self.resolve("fix widget")["selected_repo"], str(main))

    def test_explicit_worktree_path_overrides_other_active_worktree(self):
        main = self.repo("widget")
        active = self.worktree(main, "widget-A")
        target = self.worktree(main, "widget-B")
        result = self.resolve("fix " + str(target), context_directory=active)
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["selected_repo"], str(target))
        self.assertEqual(result["method"], "exact")
        self.assertEqual(len(result["candidates"]), 1)
        self.select.assert_not_called()

    def test_explicit_worktree_alias_overrides_other_active_worktree(self):
        main = self.repo("widget")
        active = self.worktree(main, "widget-A")
        target = self.worktree(main, "widget-B")
        result = self.resolve("fix widget-B", context_directory=active)
        self.assertEqual(result["selected_repo"], str(target))
        self.assertEqual(result["method"], "exact")
        self.select.assert_not_called()

    def test_quoted_worktree_path_with_spaces_overrides_active(self):
        main = self.repo("widget")
        active = self.worktree(main, "widget-A")
        target = self.worktree(main, "widget B with spaces")
        for quote in ('"', "'"):
            result = self.resolve("fix " + quote + str(target) + quote, context_directory=active)
            self.assertEqual(result["selected_repo"], str(target))
        self.select.assert_not_called()

    def test_explicit_main_path_overrides_worktree_but_generic_name_keeps_active(self):
        main = self.repo("widget")
        active = self.worktree(main, "widget-A")
        self.assertEqual(self.resolve("fix " + str(main), context_directory=active)["selected_repo"], str(main))
        self.assertEqual(self.resolve("fix widget", context_directory=active)["selected_repo"], str(active))

    def test_two_explicit_worktrees_in_same_group_clarify(self):
        main = self.repo("widget")
        first = self.worktree(main, "widget-A")
        second = self.worktree(main, "widget-B")
        result = self.resolve("fix " + str(first) + " and " + str(second), context_directory=first)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["method"], "ambiguous")
        self.select.assert_not_called()

    def test_unknown_path_basename_collision_never_routes_known_alias(self):
        main = self.repo("widget")
        before = {str(p): p.read_bytes() for p in main.rglob("*") if p.is_file()}
        requests = ["fix /unknown/widget", "fix repo /unknown/widget", "fix /tmp/unknown/widget",
                    'fix repository "/unknown folder/widget"']
        for request in requests:
            with self.subTest(request=request):
                result = self.resolve(request, context_directory=main)
                self.assertEqual(result["status"], "needs_clarification")
                self.assertIsNone(result["selected_repo"])
                receipt = json.loads(Path(result["receipt_path"]).read_text())
                self.assertEqual(receipt["reason"], "unknown_explicit_path")
        self.assertEqual(before, {str(p): p.read_bytes() for p in main.rglob("*") if p.is_file()})
        self.select.assert_not_called()

    def test_installed_workspace_preferred_only_same_group(self):
        main = self.repo("widget")
        self.workspace = self.worktree(main, "installed-widget")
        self.assertEqual(self.resolve("fix widget")["selected_repo"], str(self.workspace))
        other = self.repo("other")
        self.assertEqual(self.resolve("fix other")["selected_repo"], str(other))

    def test_semantic_match_metadata_no_paths_or_private_assignments(self):
        path = self.repo("ui-app", "# Scheduler\n\nManage appointment calendars.\n\nAPI_KEY=never-send")
        (path / "adws").mkdir()
        (path / "adws/adw_desk.py").touch()
        def select(request, candidates, **kwargs):
            encoded = json.dumps(candidates)
            self.assertNotIn(str(self.home), encoded)
            self.assertNotIn("never-send", encoded)
            self.assertIn("appointment calendars", encoded)
            self.assertIn("ADW workspace UI", encoded)
            self.assertEqual(Path(kwargs["receipt_dir"]), self.home / "run/jev")
            return dict(status="selected", selected_id=candidates[0]["id"], confidence=.81,
                        probabilities={candidates[0]["id"]: .88, "other": .12},
                        model_requested="jev-latest", model_resolved="jev-test", input_tokens=12,
                        output_tokens=3, elapsed_ms=4, receipt_path="fixture-receipt")
        self.select.side_effect = select
        result = self.resolve("change appointment calendars")
        self.assertEqual(result["selected_repo"], str(path))
        self.assertEqual(result["confidence"], .81)
        self.assertEqual(result["model_resolved"], "jev-test")

    def test_semantic_other_and_unknown_id_never_fall_back(self):
        self.repo("widget")
        for response in (dict(status="needs_clarification", selected_id=None),
                         dict(status="selected", selected_id="unknown")):
            self.select.side_effect = None
            self.select.return_value = dict(response, confidence=.9, probabilities={"other": 1},
                    model_requested="jev-latest", model_resolved="jev-test", input_tokens=1,
                    output_tokens=1, elapsed_ms=1, receipt_path="fixture")
            self.assertIsNone(self.resolve()["selected_repo"])

    def test_bounded_worker_keeps_partial_output(self):
        started = time.monotonic()
        values = router._events([sys.executable, "-c", "import time; print('{\"ok\":true}',flush=True); time.sleep(10)"], timeout=.15)
        self.assertEqual(values, [{"ok": True}])
        self.assertLess(time.monotonic() - started, 1)

    def test_real_discovery_loader_uses_actual_module_path(self):
        module = self.workspace / "adws/adw_modules/opencode_discovery.py"
        module.parent.mkdir(parents=True)
        module.write_text("from pathlib import Path\ndef discover(home):\n return {'repos': [], 'source': __file__}\n")
        with patch.object(router.jev_bridge, "status", return_value=dict(configured=False, reason="no_key")):
            self.assertEqual(router.status(self.workspace), dict(available=True, semantic_configured=False, reason="no_key"))
        # Bypass the test's discovery fake to exercise the source stdio loader.
        result = router._events([sys.executable, "-B", router._SELF, "--discover", str(module)])
        self.assertEqual(result[0]["source"], str(module))

    def test_workspace_env_and_manifest_precedence(self):
        config = self.home / ".config/opencode"
        config.mkdir(parents=True)
        (config / "opencode-adw-install.json").write_text(json.dumps(dict(workspace_root=str(self.workspace))))
        self.assertEqual(router._workspace(), str(self.workspace))
        os.environ["OPENCODE_ADW_WORKSPACE_ROOT"] = str(self.home / "override")
        self.assertEqual(router._workspace(), str(self.home / "override"))
        self.assertEqual(router._workspace(self.workspace), str(self.workspace))

    def test_metadata_filters_fences_secrets_and_hashes(self):
        value = router._clean("# Public purpose\n```\nprivate code\n```\nKEY=secret\n" + "a" * 40 + "\nAPI key: private\nUseful description")
        self.assertEqual(value, "Public purpose Useful description")

    def test_symlink_context_and_manual_root_are_canonical(self):
        path = self.repo("widget")
        alias = self.home / "linked-widget"
        alias.symlink_to(path, target_is_directory=True)
        for kwargs in (dict(context_directory=alias), dict(explicit_repo=alias)):
            self.assertEqual(self.resolve(**kwargs)["selected_repo"], str(path))

    def test_public_metadata_removes_absolute_path_fragments(self):
        candidate = dict(id="project_one", name="widget", aliases=["widget"],
                         description="Purpose with /private/never-expose and C:\\private\\hidden")
        data = json.dumps(router._public(candidate))
        self.assertNotIn("never-expose", data)
        self.assertNotIn("hidden", data)

    def test_semantic_retrieval_uses_purpose_and_caps_twelve(self):
        for index in range(13):
            self.repo("project-" + str(index))
        target = self.repo("z-last-project", "# Scheduling\n\nAppointment calendar scheduling.")
        def select(request, candidates, **kwargs):
            self.assertEqual(len(candidates), 12)
            self.assertEqual(candidates[0]["name"], target.name)
            raise router.jev_bridge.JevError("no_key")
        self.select.side_effect = select
        self.assertIsNone(self.resolve("improve appointment calendar scheduling")["selected_repo"])

    def test_discovery_failure_and_partial_catalog_are_usable(self):
        path = self.repo("widget")
        with patch.object(router, "_discover", return_value={"repos": self.repos, "truncated": True}):
            self.assertEqual(self.resolve("fix widget")["selected_repo"], str(path))
        with patch.object(router, "_discover", return_value={"repos": [], "truncated": True}):
            self.assertEqual(self.resolve()["status"], "needs_clarification")

    def test_unknown_explicit_path_does_not_use_context_or_model(self):
        path = self.repo("widget")
        result = self.resolve("fix repository /unknown/project", context_directory=path)
        self.assertIsNone(result["selected_repo"])
        self.select.assert_not_called()

    def test_endpoint_is_not_an_explicit_repository_path(self):
        path = self.repo("widget")
        self.repo("health")
        result = self.resolve("implement /health endpoint", context_directory=path)
        self.assertEqual(result["selected_repo"], str(path))

    def test_selected_project_retained_beyond_catalog_prefix(self):
        for index in range(13):
            self.repo("project-" + str(index))
        target = self.repo("z-last-project")
        result = self.resolve("fix z-last-project")
        self.assertEqual(result["candidates"][0]["selected_repo"], str(target))


if __name__ == "__main__":
    unittest.main()
