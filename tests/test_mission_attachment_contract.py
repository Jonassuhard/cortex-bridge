import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
CONSOLE = ROOT / "console"
for path in (str(ROOT), str(CONSOLE)):
    if path not in sys.path:
        sys.path.insert(0, path)

import missions  # noqa: E402


class MissionAttachmentContractTest(unittest.TestCase):
    def test_tokens_are_resolved_server_side(self):
        body = missions.MissionIn(
            objective="Inspecter",
            workspace="/tmp/cortex-demo-workspace",
            conversation_url="https://chatgpt.com/c/fixture",
            attachment_tokens=["opaque-token-123"],
        )
        descriptor = {"token": "opaque-token-123", "name": "preuve.txt", "mime": "text/plain", "kind": "file", "size_bytes": 6, "path": "/server/owned/preuve.txt"}
        with patch.object(missions, "resolve_attachment_token", return_value=descriptor) as resolver:
            self.assertEqual(missions.resolve_mission_attachments(body.attachment_tokens), [descriptor])
        resolver.assert_called_once_with("opaque-token-123")

    def test_client_paths_and_malformed_tokens_are_rejected(self):
        common = {"objective": "Inspecter", "workspace": "/tmp/cortex-demo-workspace", "conversation_url": "https://chatgpt.com/c/fixture"}
        with self.assertRaises(ValidationError):
            missions.MissionIn(**common, attachment_paths=["/Users/example/secret.txt"])
        with self.assertRaises(ValidationError):
            missions.MissionIn(**common, attachment_tokens=["../escape"])


if __name__ == "__main__":
    unittest.main()
