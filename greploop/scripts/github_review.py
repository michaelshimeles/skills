#!/usr/bin/env python3
"""Trigger and wait for a Greptile review of one GitHub PR revision."""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path


DEFAULT_BOTS = ("greptile-apps[bot]", "greptile-apps-staging[bot]")


class ReviewError(RuntimeError):
    pass


def confidence(body):
    lines = []
    fence = None
    for line in body.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            if fence is None:
                fence = marker[1]
            elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = None
        elif fence is None:
            lines.append(line)
    text = re.sub(r"</?(?:h[1-6]|p|div)\b[^>]*>", "\n", "\n".join(lines))
    text = re.sub(r"<[^>]+>", " ", text).replace("*", "").replace("#", "").replace("_", "")
    scores = set(re.findall(r"^\s*confidence(?:\s+score)?\s*:?\s*([0-5])\s*/\s*5\s*$", text, re.I | re.M))
    return int(scores.pop()) if len(scores) == 1 else None


def reviewed_commit(body):
    match = re.search(r"last reviewed commit:[^\n]*?/commit/([0-9a-f]{40})\b", body, re.I)
    return match[1].lower() if match else None


def evaluate(attempt, current_head, checks, comments, reviews):
    """Return a fresh scored review, or a reason to keep waiting."""
    if current_head != attempt["head"]:
        raise ReviewError("PR head changed; start a new attempt for the new revision")
    triggered = attempt["triggered_at"]
    old_checks = {str(item["id"]): item for item in attempt["checks"]}
    fresh_checks = []
    for check in checks:
        if "greptile" not in check.get("name", "").lower():
            continue
        if check.get("head_sha") != current_head:
            continue
        if check.get("status") != "completed":
            return {"status": "pending", "reason": "a check for the current head is still running"}
        old = old_checks.get(str(check["id"]))
        started = check.get("started_at") or ""
        if started < triggered:
            continue
        if old and started == old.get("started_at"):
            continue
        fresh_checks.append(check)

    # More than one run can exist for the same commit; use the newest attempt.
    latest = max(fresh_checks, key=lambda item: (item["started_at"], item["id"]), default=None)
    if latest and latest.get("status") != "completed":
        return {"status": "pending", "reason": "fresh check is still running"}
    if latest and latest.get("conclusion") in ("cancelled", "timed_out", "action_required", "skipped", "stale"):
        raise ReviewError(f"fresh check did not finish a review: {latest['conclusion']}")

    bots = attempt["bots"]
    old_reviews = {str(item["id"]): item for item in attempt["reviews"]}
    fresh_reviews = [
        item for item in reviews
        if item.get("user", {}).get("login") in bots
        and item.get("commit_id") == current_head
        and (item.get("submitted_at") or "") > triggered
        and item != old_reviews.get(str(item["id"]))
    ]
    candidates = []
    for review in fresh_reviews:
        if confidence(review.get("body") or "") is not None:
            candidates.append((review["submitted_at"], "review", review))

    old_comments = {str(item["id"]): item for item in attempt["comments"]}
    for comment in comments:
        if comment.get("user", {}).get("login") not in bots:
            continue
        if (comment.get("updated_at") or "") <= triggered:
            continue
        body = comment.get("body") or ""
        old = old_comments.get(str(comment["id"]))
        if old and body == old.get("body"):
            continue
        if confidence(body) is None or "too many files changed" in body.lower():
            continue
        commit = reviewed_commit(body)
        # An explicit old commit wins over unrelated fresh review activity.
        if commit != current_head and (commit is not None or not fresh_reviews):
            continue
        candidates.append((comment["updated_at"], "comment", comment))

    if not candidates:
        return {"status": "pending", "reason": "no fresh scored review tied to the current head"}
    updated, kind, result = max(candidates, key=lambda item: (item[0], item[2]["id"]))
    return {
        "status": "review_ready", "head": current_head,
        "score": confidence(result["body"]), "source": kind,
        "source_id": result["id"], "updated_at": updated,
        "body": result["body"], "url": result.get("html_url"),
        "check_id": latest["id"] if latest else None,
    }


class GitHub:
    def command(self, *args):
        result = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise ReviewError(result.stderr.strip() or "gh command failed")
        return json.loads(result.stdout)

    def pages(self, endpoint, key=None):
        pages = self.command("api", "--paginate", "--slurp", endpoint)
        return [item for page in pages for item in (page[key] if key else page)]

    def head(self, repo, pr):
        return self.command("api", f"repos/{repo}/pulls/{pr}")["head"]["sha"]

    def snapshot(self, repo, pr, head):
        return {
            "checks": self.pages(f"repos/{repo}/commits/{head}/check-runs?per_page=100&filter=all", "check_runs"),
            "comments": self.pages(f"repos/{repo}/issues/{pr}/comments?per_page=100"),
            "reviews": self.pages(f"repos/{repo}/pulls/{pr}/reviews?per_page=100"),
        }


def start(github, repo, pr, trigger, output, bots):
    # Reserve the path before posting so rerunning a command cannot post twice.
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump({"status": "preparing", "repo": repo, "pr": pr}, stream)
    head = github.head(repo, pr)
    snapshot = github.snapshot(repo, pr, head)
    if any(
        "greptile" in check.get("name", "").lower()
        and check.get("status") != "completed"
        for check in snapshot["checks"]
    ):
        raise ReviewError("Greptile is already running; let that attempt finish before starting another")
    if github.head(repo, pr) != head:
        raise ReviewError("PR head changed before the trigger; use a new attempt path")
    comment = github.command(
        "api", f"repos/{repo}/issues/{pr}/comments", "--method", "POST",
        "-f", f"body={trigger} review",
    )
    attempt = {
        "status": "triggered", "repo": repo, "pr": pr, "head": head,
        "trigger_id": comment["id"], "triggered_at": comment["created_at"],
        "bots": list(bots), **snapshot,
    }
    output.write_text(json.dumps(attempt, indent=2) + "\n")
    return {key: value for key, value in attempt.items() if key not in snapshot}


def wait_for_review(github, attempt, timeout, interval, clock=time.monotonic, sleep=time.sleep):
    if attempt.get("status") != "triggered":
        raise ReviewError("attempt has no confirmed trigger; inspect the PR before retrying")
    deadline = clock() + timeout
    while True:
        head = github.head(attempt["repo"], attempt["pr"])
        if head != attempt["head"]:
            raise ReviewError("PR head changed; start a new attempt for the new revision")
        snapshot = github.snapshot(attempt["repo"], attempt["pr"], head)
        result = evaluate(attempt, github.head(attempt["repo"], attempt["pr"]), **snapshot)
        if result["status"] == "review_ready":
            return result
        remaining = deadline - clock()
        if remaining <= 0:
            raise ReviewError(f"review timed out: {result['reason']}")
        sleep(min(interval, remaining))


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    begin = commands.add_parser("start", help="snapshot state and post one review trigger")
    begin.add_argument("--repo", required=True, help="owner/repository")
    begin.add_argument("--pr", type=positive, required=True)
    begin.add_argument("--trigger", choices=("@greptile", "@greptile-apps"), default="@greptile")
    begin.add_argument("--output", type=Path, required=True)
    begin.add_argument("--bot", action="append", help="exact trusted login; repeat for multiple bots")
    wait = commands.add_parser("wait", help="read results without posting another trigger")
    wait.add_argument("attempt", type=Path)
    wait.add_argument("--timeout", type=positive, default=600)
    wait.add_argument("--interval", type=positive, default=10)
    args = parser.parse_args()
    github = GitHub()
    try:
        if args.command == "start":
            result = start(github, args.repo, args.pr, args.trigger, args.output, args.bot or DEFAULT_BOTS)
        else:
            result = wait_for_review(github, json.loads(args.attempt.read_text()), args.timeout, args.interval)
        print(json.dumps(result, indent=2))
        return 0
    except (ReviewError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
