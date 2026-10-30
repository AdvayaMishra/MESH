"""Analyst dispositions; accepted risk remains unresolved security exposure."""

from typing import Literal

FindingState = Literal[
    "open", "triaged", "investigating", "confirmed", "false_positive", "resolved", "accepted_risk"
]
FINDING_STATES = (
    "open",
    "triaged",
    "investigating",
    "confirmed",
    "false_positive",
    "resolved",
    "accepted_risk",
)
UNRESOLVED_FINDING_STATES = ("open", "triaged", "investigating", "confirmed", "accepted_risk")
