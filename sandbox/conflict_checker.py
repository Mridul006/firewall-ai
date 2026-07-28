"""Checks a candidate rule for policy conflicts against currently-LIVE rules.

Flags conflicts for the human reviewer rather than auto-rejecting — per the
explicit design requirement, the system never silently blocks a rule on this
basis alone, it surfaces the conflict and lets the human decide. See ADR-044.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_SRC_PATTERN = re.compile(r"-s\s+([0-9./]+)")
_DST_PATTERN = re.compile(r"-d\s+([0-9./]+)")
_DPORT_PATTERN = re.compile(r"--dport\s+(\d+)")
_PROTO_PATTERN = re.compile(r"-p\s+(\w+)")
_JUMP_PATTERN = re.compile(r"-j\s+(\w+)")

# LOG never represents a real block/allow decision on its own — every real
# rule generated so far uses a LOG-before-DROP pair (rule_gen.txt explicitly
# instructs this), so it's excluded when picking a rule's *effective*
# action: the last non-LOG -j target in the command.
_NON_DECISION_TARGETS = {"LOG"}

_BLOCK_ACTIONS = {"DROP", "REJECT"}
_ALLOW_ACTIONS = {"ACCEPT"}


@dataclass
class ParsedRule:
    """The match criteria and effective action extracted from an iptables command."""

    src: str | None
    dst: str | None
    dport: int | None
    protocol: str | None
    action: str | None  # last non-LOG -j target, e.g. DROP / ACCEPT / REJECT


def _parse(command: str) -> ParsedRule:
    """Extract match fields and the effective action from an iptables command.

    Regex field extraction, not a full iptables grammar — proportionate to
    what this project's rules actually look like, mirroring tester.py's own
    _detect_chain() precedent for lightweight command parsing. A
    multi-statement command (LOG followed by DROP) is read as one logical
    rule: the LAST non-LOG -j target is its effective action.
    """
    src_match = _SRC_PATTERN.search(command)
    dst_match = _DST_PATTERN.search(command)
    dport_match = _DPORT_PATTERN.search(command)
    proto_match = _PROTO_PATTERN.search(command)

    action = None
    for target in _JUMP_PATTERN.findall(command):
        target = target.upper()
        if target not in _NON_DECISION_TARGETS:
            action = target  # last match wins

    return ParsedRule(
        src=src_match.group(1) if src_match else None,
        dst=dst_match.group(1) if dst_match else None,
        dport=int(dport_match.group(1)) if dport_match else None,
        protocol=proto_match.group(1).upper() if proto_match else None,
        action=action,
    )


def _same_match_criteria(a: ParsedRule, b: ParsedRule) -> bool:
    """True if two parsed rules match the identical traffic (src/dst/port/protocol)."""
    return (a.src, a.dst, a.dport, a.protocol) == (b.src, b.dst, b.dport, b.protocol)


def _describe(rule: ParsedRule) -> str:
    """Human-readable summary of what traffic a parsed rule matches."""
    port = f":{rule.dport}" if rule.dport else ""
    proto = f" {rule.protocol}" if rule.protocol else ""
    return f"{rule.src or 'any'} -> {rule.dst or 'any'}{port}{proto}"


def check_conflicts(candidate_command: str, live_rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare a candidate rule's match criteria against every currently-LIVE rule.

    Returns a list of conflict descriptions (empty if none). Never raises,
    never affects pass/fail — this is purely informational, surfaced to the
    human reviewer in the dashboard alongside the sandbox's fp_rate/
    detection_rate verdict.

    Two conflict types:
    - "duplicate": another LIVE rule matches identical traffic with the same
      effective action (redundant, not necessarily wrong).
    - "contradictory": another LIVE rule matches identical traffic but with
      an opposing action (one allows what the other blocks) — the one case
      that can genuinely misbehave depending on rule order/precedence.
    """
    candidate = _parse(candidate_command)
    conflicts: list[dict[str, Any]] = []

    for live in live_rules:
        live_parsed = _parse(live["command"])
        if not _same_match_criteria(candidate, live_parsed):
            continue  # different traffic entirely -- not a conflict either way

        if candidate.action is None or live_parsed.action is None:
            continue  # nothing decisive to compare (e.g. LOG-only command)

        if candidate.action == live_parsed.action:
            conflicts.append(
                {
                    "type": "duplicate",
                    "rule_id": str(live["id"]),
                    "message": (
                        f"Duplicate of already-LIVE rule {live['id']}: both "
                        f"{live_parsed.action} {_describe(candidate)}"
                    ),
                }
            )
        elif (candidate.action in _BLOCK_ACTIONS and live_parsed.action in _ALLOW_ACTIONS) or (
            candidate.action in _ALLOW_ACTIONS and live_parsed.action in _BLOCK_ACTIONS
        ):
            conflicts.append(
                {
                    "type": "contradictory",
                    "rule_id": str(live["id"]),
                    "message": (
                        f"Contradicts already-LIVE rule {live['id']}: this rule "
                        f"{candidate.action}s {_describe(candidate)}, that rule "
                        f"{live_parsed.action}s the same traffic"
                    ),
                }
            )

    if conflicts:
        logger.warning(f"Candidate rule has {len(conflicts)} policy conflict(s) with LIVE rules")

    return conflicts
