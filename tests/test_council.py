"""Council: vote aggregation (V3) and self-judging safeguard (V4)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from evaluator.council import aggregate_votes, resolve_council  # noqa: E402


# --- V3: aggregation --------------------------------------------------------

def test_majority_verdict():
    assert aggregate_votes(["PASS", "PASS", "FAIL"]) == {"verdict": "PASS", "split": True, "no_votes": False}
    assert aggregate_votes(["FAIL", "FAIL", "PASS"]) == {"verdict": "FAIL", "split": True, "no_votes": False}


def test_unanimous_is_not_split():
    assert aggregate_votes(["PASS", "PASS", "PASS"]) == {"verdict": "PASS", "split": False, "no_votes": False}
    assert aggregate_votes(["FAIL", "FAIL"]) == {"verdict": "FAIL", "split": False, "no_votes": False}
    assert aggregate_votes(["PASS"]) == {"verdict": "PASS", "split": False, "no_votes": False}


def test_split_flags_low_confidence():
    assert aggregate_votes(["PASS", "FAIL", "PASS"])["split"] is True


def test_even_council_tie_is_fail_low_confidence():
    assert aggregate_votes(["PASS", "FAIL"]) == {"verdict": "FAIL", "split": True, "no_votes": False}


def test_no_votes_is_unscored_not_split():
    # Zero votes must NOT masquerade as a split.
    assert aggregate_votes([]) == {"verdict": "FAIL", "split": False, "no_votes": True}


# --- V4: self-judging safeguard --------------------------------------------

AVAILABLE = ["claude-sonnet-4-6", "gpt-5.4", "claude-sonnet-4-5", "gpt-5.4-mini", "claude-sonnet-4-7"]
COUNCIL = ["claude-sonnet-4-6", "gpt-5.4", "claude-sonnet-4-5"]
BACKUP = "gpt-5.4-mini"


def test_no_conflict_keeps_configured_odd_council():
    r = resolve_council(COUNCIL, BACKUP, models_under_test=["gpt-5-mini"], available=AVAILABLE)
    assert r["judges"] == COUNCIL  # nothing under test; unchanged


def test_under_test_judge_is_kept_blinding_only():
    # No self-judging safeguard: a judge that is also a compared model stays.
    r = resolve_council(COUNCIL, BACKUP, models_under_test=["gpt-5.4"], available=AVAILABLE)
    assert r["judges"] == COUNCIL          # gpt-5.4 kept
    assert r["excluded"] == []             # nothing dropped for being under test


def test_all_three_judges_under_test_all_kept():
    r = resolve_council(COUNCIL, BACKUP, models_under_test=COUNCIL, available=AVAILABLE)
    assert r["judges"] == COUNCIL
    assert r["excluded"] == []


def test_even_council_restored_with_backup():
    # A 2-judge configured council (both served) gets the backup to become odd.
    r = resolve_council(
        ["gpt-5.4", "gpt-4o"], BACKUP, models_under_test=[],
        available=["gpt-5.4", "gpt-4o", "gpt-5.4-mini"],
    )
    assert len(r["judges"]) == 3 and BACKUP in r["judges"]


def test_empty_only_when_configured_all_unavailable():
    # All configured judges unavailable (not served) -> fall back to backup.
    r = resolve_council(["nope-1", "nope-2"], "gpt-4o", models_under_test=[],
                        available=["gpt-4o", "gpt-5.4"])
    assert r["judges"] == ["gpt-4o"]
    assert set(r["unavailable"]) == {"nope-1", "nope-2"}


def test_council_empty_only_when_proxy_serves_nothing():
    r = resolve_council(["a", "b"], "c", models_under_test=[], available=[])
    assert r["judges"] == []
    assert any("no judge available" in n for n in r["notes"])


def test_drops_member_not_served_by_proxy():
    r = resolve_council(
        ["claude-sonnet-4-6", "gpt-5.4", "claude-does-not-exist"],
        BACKUP,
        models_under_test=[],
        available=AVAILABLE,
    )
    assert "claude-does-not-exist" not in r["judges"]
    assert any("not served by the proxy" in n for n in r["notes"])


def test_resolve_reports_unavailable_only():
    # claude not served (unavailable); gpt-5.4 under test is still KEPT (no exclude).
    r = resolve_council(
        ["claude-sonnet-4-6", "gpt-5.4", "gpt-4o"], "gpt-5.4-mini",
        models_under_test=["gpt-5.4"],
        available=["gpt-5.4", "gpt-4o", "gpt-5.4-mini"],
    )
    assert "claude-sonnet-4-6" in r["unavailable"]
    assert r["excluded"] == []
    assert "gpt-5.4" in r["judges"] and "gpt-4o" in r["judges"]


def test_auto_picks_second_sonnet_when_configured_one_absent():
    # Configured second sonnet (4-5) absent from proxy; expect an auto-added sonnet.
    available = ["claude-sonnet-4-6", "gpt-5.4", "claude-sonnet-4-7", "gpt-5.4-mini"]
    r = resolve_council(COUNCIL, BACKUP, models_under_test=[], available=available)
    sonnets = [j for j in r["judges"] if "claude-sonnet" in j]
    assert len(sonnets) >= 2
    assert any("auto-added second claude-sonnet" in n for n in r["notes"])
