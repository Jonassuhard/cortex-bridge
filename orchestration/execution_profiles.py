"""Pure compatibility gate for future pluggable executors.

Inputs must come from trusted probes and persisted user authorization, never
from model output. A successful gate is not permission to execute, a durable
checkpoint, or proof of effects. The caller must lock the mission through
validation and dispatch and enforce workspace/policy constraints separately.
"""
from dataclasses import dataclass
import math


class ProfileError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ModelOption:
    id: str
    reflection_levels: tuple[str, ...] = ()


@dataclass(frozen=True)
class HarnessSnapshot:
    id: str
    provider: str
    cost_class: str
    observed_at: float
    available: bool
    models: tuple[ModelOption, ...]


@dataclass(frozen=True)
class ExecutionProfile:
    harness_id: str
    model_id: str
    reflection: str | None = None


def _identifier(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 256 and value == value.strip() and not any(ord(c) < 32 for c in value)


def _number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _snapshot(snapshot: HarnessSnapshot) -> None:
    if not isinstance(snapshot, HarnessSnapshot) or not all(
        _identifier(v) for v in (snapshot.id, snapshot.provider, snapshot.cost_class)
    ) or not _number(snapshot.observed_at) or type(snapshot.available) is not bool or type(snapshot.models) is not tuple:
        raise ProfileError("INVALID_OBSERVATION")
    seen = set()
    for model in snapshot.models:
        if not isinstance(model, ModelOption) or not _identifier(model.id) or model.id in seen:
            raise ProfileError("INVALID_OBSERVATION")
        levels = model.reflection_levels
        if type(levels) is not tuple or not all(_identifier(v) for v in levels) or len(set(levels)) != len(levels):
            raise ProfileError("INVALID_OBSERVATION")
        seen.add(model.id)


def _profile(profile: ExecutionProfile) -> None:
    if not isinstance(profile, ExecutionProfile) or not _identifier(profile.harness_id) or not _identifier(profile.model_id) or (profile.reflection is not None and not _identifier(profile.reflection)):
        raise ProfileError("INVALID_PROFILE")


def validate_profile(profile: ExecutionProfile, snapshot: HarnessSnapshot, *, now: float, max_age: float = 60) -> ExecutionProfile:
    """Return the exact requested selection, or reject; never substitute."""
    _profile(profile)
    _snapshot(snapshot)
    if not _number(now) or not _number(max_age):
        raise ProfileError("INVALID_OBSERVATION")
    if profile.harness_id != snapshot.id:
        raise ProfileError("HARNESS_MISMATCH")
    if not 0 <= now - snapshot.observed_at <= max_age:
        raise ProfileError("CAPABILITIES_EXPIRED")
    if not snapshot.available:
        raise ProfileError("HARNESS_UNAVAILABLE")
    model = next((m for m in snapshot.models if m.id == profile.model_id), None)
    if model is None:
        raise ProfileError("MODEL_UNAVAILABLE")
    if profile.reflection is not None and profile.reflection not in model.reflection_levels:
        raise ProfileError("REFLECTION_UNAVAILABLE")
    return profile


def validate_handoff(*, current: ExecutionProfile, target: ExecutionProfile,
                     source: HarnessSnapshot, destination: HarnessSnapshot,
                     mission_state: str, effect_states: tuple[str, ...],
                     recipient_change_approved: bool, now: float) -> ExecutionProfile:
    """Reject unsafe transitions; does not perform or persist the handoff.

    `verified` means effects reconciled by a trusted verifier; `not_applied`
    means confirmed absent. A generic failed/completed model claim is neither.
    Source capabilities may be expired: a dead provider must be escapable.
    """
    _profile(current)
    _snapshot(source)
    if current.harness_id != source.id:
        raise ProfileError("HARNESS_MISMATCH")
    if mission_state not in ("PAUSED", "PAUSED_RECOVERY_REQUIRED"):
        raise ProfileError("MISSION_NOT_PAUSED")
    if type(effect_states) is not tuple or any(state not in ("verified", "not_applied") for state in effect_states):
        raise ProfileError("EFFECT_RECONCILIATION_REQUIRED")
    validate_profile(target, destination, now=now)
    if (source.provider, source.cost_class) != (destination.provider, destination.cost_class) and recipient_change_approved is not True:
        raise ProfileError("RECIPIENT_CHANGE_APPROVAL_REQUIRED")
    return target
