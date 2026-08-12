import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from nix_control_manager.server import NcmServer, RequestHandler
from nix_control_manager.candidate_build import CandidateBuildManager


class FakeHelperAdapter:
    def status(self):
        return {
            "available": True,
            "targetId": "live",
            "readOnly": True,
            "applyEnabled": False,
            "recoveryEnabled": False,
            "activationEnabled": False,
            "dryActivatePreviewEnabled": True,
            "testActivationEnabled": True,
        }

    def validate_adoption(self):
        return {
            "source": "system-helper",
            "status": "passed",
            "checks": [],
            "warnings": [],
            "readOnly": True,
            "applyEnabled": False,
            "recoveryEnabled": False,
            "activationEnabled": False,
            "validationReceiptIssued": False,
        }

    def preview_activation(self, *, system_path, plan_fingerprint):
        return {
            "source": "system-helper",
            "status": "passed",
            "systemPath": system_path,
            "planFingerprint": plan_fingerprint,
            "sourceFilesUnchanged": True,
            "currentSystemUnchanged": True,
            "configurationWriteEnabled": False,
            "activationEnabled": False,
            "testEnabled": False,
            "switchEnabled": False,
            "dryActivateExecuted": True,
            "testActivationPrepared": True,
            "testReceipt": "R" * 32,
        }

    def test_activation(self, *, system_path, plan_fingerprint, test_receipt):
        if test_receipt != "R" * 32:
            raise ValueError("bad test receipt")
        return {
            "source": "system-helper",
            "status": "active",
            "sessionId": "c" * 24,
            "systemPath": system_path,
            "previousSystemPath": "/nix/store/" + "a" * 32 + "-previous",
            "planFingerprint": plan_fingerprint,
            "testEnabled": True,
            "switchEnabled": False,
            "configurationWriteEnabled": False,
            "autoRecoveryScheduled": True,
        }

    def recover_test_activation(self, *, session_id):
        return {
            "source": "system-helper",
            "status": "recovered",
            "sessionId": session_id,
            "currentSystemRestored": True,
            "testEnabled": True,
            "switchEnabled": False,
            "configurationWriteEnabled": False,
        }


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        directory = Path(self.temporary.name)
        self.server = NcmServer(
            ("127.0.0.1", 0),
            RequestHandler,
            state_path=directory / "state.json",
            output_path=directory / "managed.nix",
            config_root=directory / "etc-nixos",
            helper_adapter=FakeHelperAdapter(),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def request_json(self, path: str, *, method: str = "GET", body=None, token=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if token is not None:
            headers["X-NCM-Token"] = token
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        with urlopen(request, timeout=2) as response:
            return json.loads(response.read())

    def test_catalog_and_empty_state_are_available(self) -> None:
        catalog = self.request_json("/api/catalog")
        state = self.request_json("/api/state")
        system = self.request_json("/api/system")
        adoption = self.request_json("/api/adoption")
        helper = self.request_json("/api/helper")
        self.assertGreater(len(catalog), 10)
        self.assertEqual(state["packages"], [])
        self.assertEqual(system["configuration"]["mode"], "missing")
        self.assertEqual(adoption["status"], "blocked")
        self.assertFalse(adoption["safeToApply"])
        self.assertTrue(helper["available"])
        self.assertFalse(helper["applyEnabled"])

        with urlopen(self.base_url + "/", timeout=2) as response:
            html = response.read().decode("utf-8")
            self.assertIn("Nix Control Manager", html)
            self.assertIn("Content-Security-Policy", response.headers)

    def test_mutation_requires_token(self) -> None:
        with self.assertRaises(HTTPError) as context:
            self.request_json(
                "/api/save", method="POST", body={"schemaVersion": 1, "packages": []}
            )
        self.assertEqual(context.exception.code, 403)
        context.exception.close()

    def test_candidate_validation_is_authorized_and_never_enables_activation(self) -> None:
        with self.assertRaises(HTTPError) as context:
            self.request_json("/api/validate-adoption", method="POST")
        self.assertEqual(context.exception.code, 403)
        context.exception.close()

        result = self.request_json(
            "/api/validate-adoption",
            method="POST",
            token=self.server.token,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["readyForApplyProtocol"])
        self.assertFalse(result["activationEnabled"])

    def test_helper_validation_requires_token_and_exposes_no_apply_capability(self) -> None:
        with self.assertRaises(HTTPError) as context:
            self.request_json("/api/helper/validate-adoption", method="POST")
        self.assertEqual(context.exception.code, 403)
        context.exception.close()

        result = self.request_json(
            "/api/helper/validate-adoption",
            method="POST",
            token=self.server.token,
        )
        self.assertEqual(result["source"], "system-helper")
        self.assertEqual(result["status"], "passed")
        self.assertFalse(result["validationReceiptIssued"])
        self.assertFalse(result["applyEnabled"])

    def test_save_writes_validated_files(self) -> None:
        result = self.request_json(
            "/api/save",
            method="POST",
            token=self.server.token,
            body={"schemaVersion": 1, "packages": ["firefox"], "options": {}},
        )
        self.assertTrue(result["saved"])
        self.assertIn("pkgs.firefox", self.server.output_path.read_text(encoding="utf-8"))
        self.assertEqual(
            json.loads(self.server.state_path.read_text(encoding="utf-8"))["packages"],
            ["firefox"],
        )

    def test_build_preview_requires_token_and_streams_a_fixed_job(self) -> None:
        root = self.server.config_root
        root.mkdir(exist_ok=True)
        (root / "configuration.nix").write_text(
            "{ ... }: {\n  imports = [\n    ./ncm\n  ];\n}\n", encoding="utf-8"
        )
        managed = root / "ncm"
        managed.mkdir()
        (managed / "default.nix").write_text(
            "{ ... }: { imports = [ ./packages.nix ]; }\n", encoding="utf-8"
        )
        (managed / "packages.nix").write_text(
            "{ pkgs, ... }: { environment.systemPackages = with pkgs; [ ]; }\n",
            encoding="utf-8",
        )
        (managed / "state.json").write_text(
            '{"schemaVersion":1,"packages":{},"options":{}}', encoding="utf-8"
        )

        def executor(command, cwd, cancel_event, line_sink):
            line_sink("stderr", "streamed build line")
            output = "/nix/store/" + "b" * 32 + "-preview"
            line_sink("stdout", output)
            return 0, (output,)

        self.server.build_manager.close()
        self.server.build_manager = CandidateBuildManager(
            config_root=root,
            executor=executor,
            which=lambda name: f"/tools/{name}",
        )

        with self.assertRaises(HTTPError) as context:
            self.request_json("/api/build-preview", method="POST")
        self.assertEqual(context.exception.code, 403)
        context.exception.close()

        started = self.request_json(
            "/api/build-preview", method="POST", token=self.server.token
        )
        job_id = started["jobId"]
        deadline = time.monotonic() + 3
        result = started
        while result["cancellable"] and time.monotonic() < deadline:
            result = self.request_json(
                f"/api/build-preview/{job_id}?after={result['nextCursor']}"
            )
            time.sleep(0.01)
        self.assertEqual(result["status"], "passed")
        self.assertFalse(result["activationEnabled"])
        self.assertFalse(result["configurationWriteEnabled"])
        latest = self.request_json("/api/build-preview")
        self.assertEqual(latest["jobId"], job_id)
        self.assertEqual(latest["status"], "passed")
        dry = self.request_json(
            "/api/helper/activation-preview",
            method="POST",
            token=self.server.token,
        )
        self.assertEqual(dry["systemPath"], result["outputPaths"][0])
        self.assertTrue(dry["dryActivateExecuted"])
        self.assertFalse(dry["activationEnabled"])
        active = self.request_json(
            "/api/helper/test-activation",
            method="POST",
            body={"testReceipt": dry["testReceipt"]},
            token=self.server.token,
        )
        self.assertEqual(active["status"], "active")
        self.assertFalse(active["switchEnabled"])
        recovered = self.request_json(
            "/api/helper/recover-test-activation",
            method="POST",
            body={"sessionId": active["sessionId"]},
            token=self.server.token,
        )
        self.assertEqual(recovered["status"], "recovered")
        self.assertTrue(recovered["currentSystemRestored"])


if __name__ == "__main__":
    unittest.main()
