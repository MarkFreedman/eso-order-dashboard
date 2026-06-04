"""Unwrap extraction result fields and track confidence warnings.

Extraction JSON uses inconsistent formats: some fields are
{"value": X, "confidence": "HIGH"} dicts, others are plain strings/numbers.
This module normalizes access to both.
"""


def get_value(field, default=""):
    """Extract the value from a field, whether it's a wrapper dict or plain."""
    if field is None:
        return default
    if isinstance(field, dict) and "value" in field:
        val = field["value"]
        return val if val is not None else default
    return field


def get_confidence(field):
    """Return the confidence level for a field. Plain values default to HIGH."""
    if isinstance(field, dict) and "confidence" in field:
        return field["confidence"]
    return "HIGH"


class Warnings:
    """Accumulates warnings during order processing."""

    def __init__(self):
        self.items = []

    def add(self, message):
        self.items.append(message)

    def check_confidence(self, field_name, field_data):
        """Log a warning if confidence is LOW or MISSING. Returns the extracted value."""
        conf = get_confidence(field_data)
        val = get_value(field_data)
        if conf in ("LOW", "MISSING"):
            self.items.append(f"{field_name}: confidence={conf}, value={val!r}")
        return val
