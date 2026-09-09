"""No provider access: compatibility and transition decisions only."""
import dataclasses
import unittest

try:
    from orchestration import execution_profiles as profiles
except ImportError:
    profiles = None


class ExecutionProfileTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(profiles, "execution profile gate is not implemented")
        self.model = profiles.ModelOption("model-a", ("low", "high"))
        self.source = profiles.HarnessSnapshot("harness-a", "provider-a", "included", 100.0, True, (self.model,))
        self.profile = profiles.ExecutionProfile("harness-a", "model-a", "high")

    def rejected(self, code, fn, *args, **kwargs):
        with self.assertRaises(profiles.ProfileError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_observed_profile_is_preserved_without_fallback(self):
        self.assertEqual(profiles.validate_profile(self.profile, self.source, now=110), self.profile)

    def test_unknown_model_is_not_replaced(self):
        self.rejected("MODEL_UNAVAILABLE", profiles.validate_profile,
                      dataclasses.replace(self.profile, model_id="other"), self.source, now=110)

    def test_reflection_must_be_observed(self):
        self.rejected("REFLECTION_UNAVAILABLE", profiles.validate_profile,
                      dataclasses.replace(self.profile, reflection="max"), self.source, now=110)

    def test_unspecified_reflection_does_not_invent_a_default(self):
        p = dataclasses.replace(self.profile, reflection=None)
        self.assertIsNone(profiles.validate_profile(p, self.source, now=110).reflection)

    def test_wrong_harness_is_not_rerouted(self):
        self.rejected("HARNESS_MISMATCH", profiles.validate_profile,
                      dataclasses.replace(self.profile, harness_id="other"), self.source, now=110)

    def test_unavailable_snapshot_cannot_be_selected(self):
        self.rejected("HARNESS_UNAVAILABLE", profiles.validate_profile,
                      self.profile, dataclasses.replace(self.source, available=False), now=110)

    def test_stale_and_future_observations_fail_closed(self):
        for observed in (49, 111):
            with self.subTest(observed=observed):
                self.rejected("CAPABILITIES_EXPIRED", profiles.validate_profile,
                              self.profile, dataclasses.replace(self.source, observed_at=observed), now=110)

    def test_bad_clock_and_age_cannot_disable_freshness_gate(self):
        for now, age in ((float("nan"), 60), (float("inf"), 60), (True, 60), (110, float("nan")), (110, -1), (110, True)):
            with self.subTest(now=now, age=age):
                self.rejected("INVALID_OBSERVATION", profiles.validate_profile,
                              self.profile, self.source, now=now, max_age=age)

    def test_malformed_catalog_is_rejected(self):
        for changes in ({"available": "true"}, {"observed_at": float("nan")}, {"models": (self.model, self.model)}, {"provider": ""}, {"models": (profiles.ModelOption("model-a", ("high", "high")),)}):
            with self.subTest(changes=changes):
                self.rejected("INVALID_OBSERVATION", profiles.validate_profile,
                              self.profile, dataclasses.replace(self.source, **changes), now=110)

    def handoff(self, **changes):
        arguments = dict(current=self.profile, target=self.profile, source=self.source,
                         destination=self.source, mission_state="PAUSED", effect_states=("verified", "not_applied"),
                         recipient_change_approved=False, now=110)
        arguments.update(changes)
        return profiles.validate_handoff(**arguments)

    def test_paused_reconciled_transition_preserves_selection(self):
        self.assertEqual(self.handoff(), self.profile)

    def test_running_or_terminal_mission_cannot_handoff(self):
        for state in ("EXECUTING_LOCAL_ACTION", "COMPLETED", "IDLE", "unknown"):
            with self.subTest(state=state):
                self.rejected("MISSION_NOT_PAUSED", self.handoff, mission_state=state)

    def test_uncertain_failed_or_running_effect_blocks_handoff(self):
        for state in ("running", "unknown", "failed", "pending", "completed", None):
            with self.subTest(state=state):
                self.rejected("EFFECT_RECONCILIATION_REQUIRED", self.handoff, effect_states=(state,))

    def test_provider_or_cost_change_requires_explicit_approval(self):
        for changes in ({"provider": "other"}, {"cost_class": "paid"}):
            destination = dataclasses.replace(self.source, **changes)
            for approval in (False, 1, "yes"):
                self.rejected("RECIPIENT_CHANGE_APPROVAL_REQUIRED", self.handoff,
                              destination=destination, recipient_change_approved=approval)
            self.assertEqual(self.handoff(destination=destination, recipient_change_approved=True), self.profile)

    def test_approval_does_not_override_unsupported_target(self):
        self.rejected("MODEL_UNAVAILABLE", self.handoff,
                      target=dataclasses.replace(self.profile, model_id="missing"), recipient_change_approved=True)

    def test_expired_source_can_be_left_without_claiming_it_is_ready(self):
        self.assertEqual(self.handoff(source=dataclasses.replace(self.source, observed_at=1, available=False)), self.profile)

    def test_source_identity_must_match_current_selection(self):
        self.rejected("HARNESS_MISMATCH", self.handoff,
                      current=dataclasses.replace(self.profile, harness_id="foreign"))


if __name__ == "__main__":
    unittest.main()
