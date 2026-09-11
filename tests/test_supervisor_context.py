"""Bounded context packets for the desktop ChatGPT supervisor."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestration.context import (  # noqa: E402
    ContextPacketError,
    build_context_packet,
    render_context_packet,
    render_supervisor_prompt,
    render_supervisor_report,
    validate_context_packet,
)
from orchestration.runner import render_contract, render_desktop_supervisor_prompt  # noqa: E402


class SupervisorContextTestCase(unittest.TestCase):
    def test_free_text_redacts_absolute_paths_before_rendering(self):
        packet = build_context_packet(
            goal="Inspecter /Users/alice/project/src/app.py",
            conversation_text="Le rapport local est dans /private/tmp/cortex-report.json",
            facts=[{
                "value": "workspace=/Volumes/ARCHIVE/project",
                "source": "manual fixture",
                "confidence": "verified",
            }],
        )
        rendered = render_context_packet(packet)
        self.assertNotIn("/Users/", rendered)
        self.assertNotIn("/private/", rendered)
        self.assertNotIn("/Volumes/", rendered)
        self.assertNotIn("/home/", rendered)
        self.assertIn("[REDACTED_PATH]", rendered)

    def test_relevant_packet_is_redacted_deduplicated_and_renderable(self):
        packet = build_context_packet(
            goal="Corriger la synchronisation",
            conversation_text="Le token=top-secret ne doit pas sortir. Voici le fait utile.",
            facts=[{"value": "paired=false", "source": "GET /api/chrome-extension/status", "confidence": "verified"}],
            available_context=[
                {
                    "kind": "file",
                    "path": "frontend/components/CortexApp.tsx",
                    "size_bytes": 1200,
                    "sha256": "a" * 64,
                    "reason": "Source de l'état de connexion",
                },
                {
                    "kind": "file",
                    "path": "frontend/components/CortexApp.tsx",
                    "size_bytes": 1200,
                    "sha256": "a" * 64,
                    "reason": "Doublon à supprimer",
                },
                {
                    "kind": "link",
                    "url": "https://example.com/reference",
                    "reason": "Documentation de référence",
                },
            ],
            capabilities=["read_file", "run_tests"],
        )

        self.assertEqual(packet["conversation"]["mode"], "relevant_excerpt")
        self.assertNotIn("top-secret", packet["conversation"]["text"])
        self.assertEqual(len(packet["available_context"]), 2)
        self.assertEqual(packet["available_context"][0]["transmission"], "proposal_required")
        rendered = json.loads(render_context_packet(packet))
        self.assertEqual(rendered["goal"], "Corriger la synchronisation")

    def test_full_transcript_requires_explicit_consent(self):
        with self.assertRaisesRegex(ContextPacketError, "FULL_TRANSCRIPT_CONSENT_REQUIRED"):
            build_context_packet(
                goal="Inspecter la conversation",
                conversation_text="échange complet",
                conversation_mode="full_with_consent",
            )

        packet = build_context_packet(
            goal="Inspecter la conversation",
            conversation_text="échange complet",
            conversation_mode="full_with_consent",
            conversation_consent=True,
        )
        self.assertEqual(packet["conversation"]["mode"], "full_with_consent")

    def test_unsafe_context_is_rejected(self):
        absolute_fixture = "/" + "Users" + "/private/secret.txt"
        file_url_fixture = "file://" + absolute_fixture
        cases = [
            {"kind": "file", "path": absolute_fixture, "reason": "x"},
            {"kind": "file", "path": "../secret.txt", "reason": "x"},
            {"kind": "link", "url": file_url_fixture, "reason": "x"},
            {"kind": "link", "url": "javascript:alert(1)", "reason": "x"},
            {"kind": "image", "path": "capture.png", "reason": "x"},
        ]
        for item in cases:
            with self.subTest(item=item):
                with self.assertRaises(ContextPacketError):
                    build_context_packet(goal="x", available_context=[item])

    def test_contract_includes_context_packet_without_changing_protocol(self):
        packet = build_context_packet(
            goal="Lire un fichier",
            available_context=[
                {"kind": "file", "path": "README.md", "reason": "Contexte"},
            ],
        )
        contract = render_contract(
            "Lire un fichier",
            "mission-1",
            "/workspace",
            context_packet=render_context_packet(packet),
        )
        self.assertIn("Context packet:", contract)
        self.assertIn("README.md", contract)
        self.assertIn("REQUEST_CONTEXT", contract)
        self.assertIn("Workspace: <authorized-workspace>", contract)
        self.assertNotIn("/workspace", contract)

    def test_serialized_packet_is_revalidated_before_transport(self):
        packet = build_context_packet(
            goal="Vérifier le build",
            conversation_text="token=secret",
            available_context=[{"kind": "file", "path": "README.md", "reason": "Contexte"}],
        )
        validated = validate_context_packet(json.loads(render_context_packet(packet)))
        self.assertEqual(validated["goal"], "Vérifier le build")
        self.assertNotIn("secret", validated["conversation"]["text"])

        with self.assertRaises(ContextPacketError):
            validate_context_packet({"protocol": "other.v1"})

        tampered = dict(packet)
        tampered["available_context"] = [{"kind": "file", "path": "../secret", "reason": "x"}]
        with self.assertRaises(ContextPacketError):
            render_context_packet(tampered)

    def test_supervisor_prompt_is_pure_bounded_and_explicit_about_desktop_limits(self):
        packet = build_context_packet(
            goal="Vérifier le rapport",
            conversation_text="token=secret à ne pas transmettre",
            available_context=[
                {"kind": "file", "path": "reports/result.txt", "reason": "Preuve"},
            ],
        )
        prompt = render_supervisor_prompt(packet, "Répondre avec un bloc cortex-decision.")
        self.assertIn("Capability boundary:", prompt)
        self.assertIn("native attachment capability is not exposed", prompt)
        self.assertIn("reports/result.txt", prompt)
        self.assertNotIn("token=secret", prompt)
        self.assertNotIn("/Users/", prompt)
        self.assertEqual(
            render_desktop_supervisor_prompt(packet, "Répondre avec un bloc cortex-decision."),
            prompt,
        )

    def test_supervisor_report_separates_evidence_unknowns_and_safe_next_step(self):
        report = json.loads(
            render_supervisor_report(
                "SUCCEEDED",
                requested_action="Lire le rapport",
                executed_action="read_file",
                command="read reports/result.txt",
                result="OK token=hidden",
                evidence=["reports/result.txt", "tests passed"],
                unknowns=["Le backend desktop reste non exposé"],
                next_safe_action="Demander l'approbation de la capture",
            )
        )
        self.assertEqual(report["protocol"], "desktop-supervisor-report.v1")
        self.assertEqual(report["status"], "SUCCEEDED")
        self.assertEqual(report["evidence"][0], "reports/result.txt")
        self.assertIn("[REDACTED]", report["result"])
        absolute_report_fixture = "/" + "Users" + "/private/result.txt"
        with self.assertRaisesRegex(ContextPacketError, "UNSAFE_REPORT"):
            render_supervisor_report(
                "SUCCEEDED",
                requested_action="Lire",
                evidence=[absolute_report_fixture],
            )


if __name__ == "__main__":
    unittest.main()
