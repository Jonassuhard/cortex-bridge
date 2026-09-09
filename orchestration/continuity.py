"""Versioned explicit working context. Never an execution authorization."""
import hashlib
import json

EVENT_TYPE = "context.checkpoint.v1"
CONTEXT_KEYS = frozenset({"constraints", "decisions", "open_questions", "next_action"})


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def validate_context(context: object) -> dict:
    if type(context) is not dict or set(context) != CONTEXT_KEYS:
        raise ValueError("INVALID_CONTEXT")
    for key in ("constraints", "decisions", "open_questions"):
        if type(context[key]) is not list or any(type(v) is not str or not v.strip() for v in context[key]):
            raise ValueError("INVALID_CONTEXT")
    if type(context["next_action"]) is not str or not context["next_action"].strip():
        raise ValueError("INVALID_CONTEXT")
    try:
        encoded = canonical(context).encode("utf-8")
    except (ValueError, UnicodeError):
        raise ValueError("INVALID_CONTEXT") from None
    if len(encoded) > 65536:
        raise ValueError("INVALID_CONTEXT")
    return json.loads(encoded)


def envelope(mission_id: str, source_digest: str, context: dict) -> dict:
    body = dict(schema_version=1, mission_id=mission_id, source_digest=source_digest,
                context=validate_context(context))
    return {**body, "digest": digest(body)}


def verify(envelope_value: object, mission_id: str) -> dict:
    try:
        if type(envelope_value) is not dict or set(envelope_value) != {"schema_version", "mission_id", "source_digest", "context", "digest"}:
            raise ValueError()
        body = {k: v for k, v in envelope_value.items() if k != "digest"}
        if type(body["schema_version"]) is not int or body["schema_version"] != 1 or body["mission_id"] != mission_id:
            raise ValueError()
        validate_context(body["context"])
        source = body["source_digest"]
        if type(source) is not str or len(source) != 64 or any(c not in "0123456789abcdef" for c in source):
            raise ValueError()
        if digest(body) != envelope_value["digest"]:
            raise ValueError()
        return envelope_value
    except (ValueError, TypeError, UnicodeError):
        raise ValueError("CONTEXT_INTEGRITY_ERROR") from None
