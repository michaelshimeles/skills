# GitHub review attempts

`REVIEW` below is the absolute path to `scripts/github_review.py` inside the
installed `greploop` skill. Run it from the target repository with authenticated
`gh`. Both trigger names use this same implementation.

## Start and wait

After pushing, use a new artifact path for each cycle:

```bash
python3 "$REVIEW" start --repo OWNER/REPO --pr 123 \
  --trigger @greptile --output .artifacts/greploop/attempt-1.json
python3 "$REVIEW" wait .artifacts/greploop/attempt-1.json \
  --timeout 600 --interval 10
```

`start` posts a PR comment. Use it only when the task authorizes the review
loop. Pass `--trigger @greptile-apps` for the alternate route. The helper
snapshots checks, comments, and reviews before posting and records the trigger's
server timestamp and current head. It refuses to overwrite an attempt file.
If start fails after posting, inspect the PR and saved state before retrying;
use `wait` on a confirmed attempt instead of posting again.
If a Greptile check is already running, start refuses to post another trigger.
Let that run finish, then use a new attempt path to request a fresh review.

`wait` is read-only. It paginates all result sources, verifies the head before
and after reading, and rejects old completed checks and unchanged summaries.
A scored review must be newer than the trigger and tied to the head through a
review's `commit_id` or the summary's explicit last-reviewed-commit link. A
fresh summary without either association remains pending. This also permits
large-PR reviews that update a summary without creating a check run.

A fresh running check keeps the attempt pending. A cancelled, skipped, stale,
or timed-out check stops it. Review findings can accompany a failed check, so
read the score and body instead of equating check success with code correctness.
The helper's `review_ready` result means fresh feedback is available; it does
not certify that the PR is ready to merge.

The default trusted logins are `greptile-apps[bot]` and
`greptile-apps-staging[bot]`. For another installation, verify its identity and
pass repeatable `--bot EXACT_LOGIN` arguments to `start`.

If a provider omits revision metadata, report that freshness could not be
verified. Do not substitute the PR description or an arbitrary `5/5` string.

## Inspect and resolve findings

Read the returned `body` and all general-comment findings. Then use the
[GraphQL reference](graphql-queries.md) to fetch unresolved threads. Follow
`pageInfo.endCursor` until `hasNextPage` is false. Identify Greptile by its exact
trusted author login. GraphQL may omit the `[bot]` suffix shown by REST;
verify the bot's GraphQL identity before filtering threads. Read full thread discussions before deciding a finding
is addressed; the initial query only returns a few comments per thread.

Use `isResolved` on review threads for resolution state. The REST inline
comments endpoint does not provide that state. Keep unresolved older threads
in the review, even if their original commit differs from the current head.
After checking and publishing fixes, resolve only the addressed thread IDs.
Fetch again to confirm the final unresolved count and verify the head still
matches the reviewed revision before reporting success.

API fields: [check runs](https://docs.github.com/en/rest/checks/runs),
[PR reviews](https://docs.github.com/en/rest/pulls/reviews).
