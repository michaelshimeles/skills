import copy
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "greploop/scripts/github_review.py"
SPEC = importlib.util.spec_from_file_location("github_review", SCRIPT)
REVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REVIEW)
HEAD = "a" * 40
OLD_HEAD = "b" * 40
BOT = "greptile-apps[bot]"
BEFORE = "2026-09-06T10:00:00Z"
TRIGGER = "2026-09-06T10:01:00Z"
AFTER = "2026-09-06T10:02:00Z"


def summary(score=5, commit=HEAD, **overrides):
    body = f"<h3>Confidence Score: {score}/5</h3>\nReview details\n"
    if commit:
        body += f"Last reviewed commit: [change](https://github.com/owner/repo/commit/{commit})"
    return {"id": 10, "user": {"login": BOT}, "updated_at": AFTER, "body": body, **overrides}


def check(**overrides):
    return {
        "id": 1, "name": "Greptile", "head_sha": HEAD, "status": "completed",
        "conclusion": "success", "started_at": BEFORE, **overrides,
    }


def attempt(**overrides):
    return {
        "status": "triggered", "repo": "owner/repo", "pr": 123, "head": HEAD,
        "triggered_at": TRIGGER, "bots": [BOT], "checks": [check()],
        "comments": [summary(updated_at=BEFORE)], "reviews": [], **overrides,
    }


def evaluate(state=None, checks=None, comments=None, reviews=None):
    return REVIEW.evaluate(state or attempt(), HEAD, checks or [], comments or [], reviews or [])


def test_old_completed_check_and_score_do_not_complete_a_new_attempt():
    result = evaluate(checks=[check()], comments=[summary(updated_at=BEFORE)])
    assert result["status"] == "pending"


def test_stale_running_check_cannot_block_a_fresh_scored_review():
    old = check(status="in_progress")
    review = {"id": 2, "user": {"login": BOT}, "commit_id": HEAD, "submitted_at": AFTER, "body": "Confidence: 5/5"}
    result = evaluate(state=attempt(checks=[old]), checks=[old], reviews=[review])
    assert (result["status"], result["score"]) == ("review_ready", 5)


def test_timestamp_only_edit_cannot_refresh_an_old_score():
    assert evaluate(comments=[summary()])["status"] == "pending"


def test_fresh_successful_check_cannot_refresh_an_old_score():
    result = evaluate(checks=[check(id=2, started_at=AFTER)], comments=[summary(updated_at=BEFORE)])
    assert result["status"] == "pending"


def test_same_commit_edited_summary_is_accepted_without_a_check_run():
    result = evaluate(state=attempt(comments=[summary(score=3, updated_at=BEFORE)]), comments=[summary()])
    assert result["status"] == "review_ready"
    assert result["score"] == 5
    assert result["head"] == HEAD
    assert result["check_id"] is None


@pytest.mark.parametrize("commit", [OLD_HEAD, None])
def test_new_summary_must_identify_the_current_revision(commit):
    assert evaluate(comments=[summary(id=11, commit=commit)])["status"] == "pending"


def test_empty_fresh_review_cannot_associate_a_summary_without_a_commit_link():
    review = {"id": 2, "user": {"login": BOT}, "commit_id": HEAD, "submitted_at": AFTER, "body": ""}
    result = evaluate(comments=[summary(id=11, commit=None)], reviews=[review])
    assert result["status"] == "pending"
    # A summary explicitly naming an older commit cannot borrow this association.
    assert evaluate(comments=[summary(id=11, commit=OLD_HEAD)], reviews=[review])["status"] == "pending"


def test_scored_review_supplies_its_own_score_instead_of_borrowing_a_markerless_summary():
    review = {"id": 2, "user": {"login": BOT}, "commit_id": HEAD, "submitted_at": AFTER, "body": "Confidence: 3/5"}
    result = evaluate(comments=[summary(id=11, commit=None)], reviews=[review])
    assert (result["status"], result["source"], result["score"]) == ("review_ready", "review", 3)


@pytest.mark.parametrize("overrides", [
    {"commit_id": OLD_HEAD}, {"submitted_at": BEFORE}, {"user": {"login": "greptile-imposter"}},
])
def test_unrelated_review_cannot_associate_a_summary(overrides):
    review = {"id": 2, "user": {"login": BOT}, "commit_id": HEAD, "submitted_at": AFTER, "body": "", **overrides}
    assert evaluate(comments=[summary(id=11, commit=None)], reviews=[review])["status"] == "pending"


def test_a_fresh_scored_review_can_be_the_result():
    review = {"id": 2, "user": {"login": BOT}, "commit_id": HEAD, "submitted_at": AFTER, "body": "Confidence: 3/5"}
    result = evaluate(reviews=[review])
    assert (result["status"], result["score"], result["source"]) == ("review_ready", 3, "review")


def test_newest_running_check_wins_over_completed_checks():
    checks = [check(id=2, started_at=AFTER), check(id=3, started_at=AFTER, status="in_progress")]
    assert evaluate(checks=checks, comments=[summary(id=11)])["status"] == "pending"


def test_same_check_id_with_a_new_start_time_is_a_new_attempt():
    result = evaluate(checks=[check(started_at=AFTER, status="in_progress")], comments=[summary(id=11)])
    assert result["status"] == "pending"


def test_check_started_in_the_trigger_second_still_blocks_a_summary():
    result = evaluate(checks=[check(id=2, started_at=TRIGGER, status="in_progress")], comments=[summary(id=11)])
    assert result["status"] == "pending"


@pytest.mark.parametrize("conclusion", ["cancelled", "timed_out", "action_required", "skipped", "stale"])
def test_aborted_fresh_check_stops_the_attempt(conclusion):
    with pytest.raises(REVIEW.ReviewError, match="did not finish"):
        evaluate(checks=[check(id=2, started_at=AFTER, conclusion=conclusion)], comments=[summary(id=11)])


def test_bot_identity_and_confidence_label_are_required():
    assert evaluate(comments=[summary(id=11, user={"login": "greptile-helper"})])["status"] == "pending"
    assert REVIEW.confidence("There were 5/5 tests passing") is None


@pytest.mark.parametrize("body", ["Confidence: 4/5", "**Confidence Score: 4/5**", "<h3>Confidence Score: 4/5</h3>"])
def test_confidence_formats(body):
    assert REVIEW.confidence(body) == 4


def test_confidence_ignores_prose_quotes_and_fenced_examples():
    body = '''The skill aims for Confidence Score: 5/5 before shipping.
> Confidence Score: 5/5
```text
Confidence Score: 5/5
```
<h3>Confidence Score: 3/5</h3>
'''
    assert REVIEW.confidence(body) == 3


def test_conflicting_score_headings_are_not_guessed():
    assert REVIEW.confidence("Confidence Score: 5/5\nConfidence Score: 3/5") is None


def test_head_change_invalidates_attempt():
    with pytest.raises(REVIEW.ReviewError, match="head changed"):
        REVIEW.evaluate(attempt(), OLD_HEAD, [], [summary(id=11)], [])


class FakeGitHub:
    def __init__(self, snapshots=None, heads=None):
        self.snapshots = snapshots or [{"checks": [], "comments": [], "reviews": []}]
        self.heads = heads or [HEAD]
        self.posts = []
        self.polls = 0

    def head(self, *_args):
        return self.heads.pop(0) if len(self.heads) > 1 else self.heads[0]

    def snapshot(self, *_args):
        self.polls += 1
        return copy.deepcopy(self.snapshots.pop(0) if len(self.snapshots) > 1 else self.snapshots[0])

    def command(self, *args):
        self.posts.append(args)
        return {"id": 99, "created_at": TRIGGER}


def test_start_records_baseline_and_posts_the_selected_trigger_only_once(tmp_path):
    github = FakeGitHub()
    path = tmp_path / "attempt.json"
    REVIEW.start(github, "owner/repo", 123, "@greptile-apps", path, [BOT])
    saved = json.loads(path.read_text())
    assert (saved["head"], saved["trigger_id"], saved["triggered_at"]) == (HEAD, 99, TRIGGER)
    assert "body=@greptile-apps review" in github.posts[0]
    with pytest.raises(FileExistsError):
        REVIEW.start(github, "owner/repo", 123, "@greptile-apps", path, [BOT])
    assert len(github.posts) == 1


def test_start_does_not_interrupt_an_existing_review(tmp_path):
    github = FakeGitHub([{"checks": [check(status="in_progress")], "comments": [], "reviews": []}])
    with pytest.raises(REVIEW.ReviewError, match="already running"):
        REVIEW.start(github, "owner/repo", 123, "@greptile", tmp_path / "attempt.json", [BOT])
    assert not github.posts


def test_start_does_not_post_if_head_changes_during_snapshot(tmp_path):
    github = FakeGitHub(heads=[HEAD, OLD_HEAD])
    with pytest.raises(REVIEW.ReviewError, match="head changed"):
        REVIEW.start(github, "owner/repo", 123, "@greptile", tmp_path / "attempt.json", [BOT])
    assert not github.posts


def test_wait_polls_until_fresh_feedback_without_posting():
    github = FakeGitHub([
        {"checks": [check()], "comments": [summary(updated_at=BEFORE)], "reviews": []},
        {"checks": [], "comments": [summary(id=11)], "reviews": []},
    ])
    result = REVIEW.wait_for_review(github, attempt(), 10, 1, sleep=lambda _: None)
    assert result["score"] == 5
    assert github.polls == 2
    assert not github.posts


def test_wait_stops_at_deadline_instead_of_reusing_stale_results():
    github = FakeGitHub()
    ticks = iter([0, 1, 2])
    with pytest.raises(REVIEW.ReviewError, match="timed out"):
        REVIEW.wait_for_review(github, attempt(), 2, 1, clock=lambda: next(ticks), sleep=lambda _: None)
    assert github.polls == 2
    assert not github.posts


def test_wait_checks_head_again_after_fetching_results():
    github = FakeGitHub([{"checks": [], "comments": [summary(id=11)], "reviews": []}], heads=[HEAD, OLD_HEAD])
    with pytest.raises(REVIEW.ReviewError, match="head changed"):
        REVIEW.wait_for_review(github, attempt(), 10, 1)


def test_paginated_api_results_include_later_pages(monkeypatch):
    github = REVIEW.GitHub()
    monkeypatch.setattr(github, "command", lambda *args: [{"check_runs": [check()]}, {"check_runs": [check(id=2)]}])
    assert [item["id"] for item in github.pages("endpoint", "check_runs")] == [1, 2]
    monkeypatch.setattr(github, "command", lambda *args: [[summary()], [summary(id=11)]])
    assert [item["id"] for item in github.pages("endpoint")] == [10, 11]


def test_api_errors_are_reported_instead_of_treated_as_missing_reviews(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 1, "", "HTTP 403"))
    with pytest.raises(REVIEW.ReviewError, match="HTTP 403"):
        REVIEW.GitHub().snapshot("owner/repo", 123, HEAD)
