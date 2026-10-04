# GitLab reviews

Use the configured `glab` instance and MR source branch. `--trigger` from the
shared workflow determines the mention; `@greptile` is the default. Do not
infer that Greptile is running from unrelated CI pipelines.

## Start an attempt

Read `glab mr view IID --output json` and record the MR's `sha`. Snapshot all
pages of notes before posting, including IDs, bodies, and update timestamps.
Verify the configured bot's exact username once, then use that identity.

```bash
glab api 'projects/:fullpath/merge_requests/IID/notes?per_page=100&page=1'
glab api --method POST 'projects/:fullpath/merge_requests/IID/notes' \
  --field 'body=@greptile review'
```

Record the returned trigger note's ID and `created_at`. Use the alternate
mention when requested. For multiline messages, use a file or structured API
argument that preserves the text.

## Wait for feedback

Poll notes at 10-second intervals, with a 10-minute deadline. Paginate until a
page contains fewer than 100 notes. Read the current SHA before and after each
poll. Stop if it changed. Only accept a new or changed bot summary updated
strictly after the trigger and explicitly associated with that SHA by the
site's review metadata or a last-reviewed-commit link. An older `5/5`, a
changed timestamp alone, or a successful CI pipeline is insufficient.

If the integration exposes a Greptile job, also record its attempt ID and
start time. Wait for the new job to finish; do not reuse an older completed job
for the same SHA. Cancelled or timed-out jobs stop the attempt. If the site
exposes no way to associate feedback with the requested revision, report that
limitation and stop rather than declaring a fresh review.

## Read and resolve discussions

```bash
glab api 'projects/:fullpath/merge_requests/IID/discussions?per_page=100&page=1'
```

Paginate all discussions. Resolution fields belong to each note: select notes
with `resolvable == true` and `resolved == false` from the trusted bot. Read the
whole discussion, including replies, before acting. Keep unresolved findings
from earlier commits; a push does not resolve them.

After checks pass and a fix is published, resolve its discussion:

```bash
glab api --method PUT \
  'projects/:fullpath/merge_requests/IID/discussions/DISCUSSION_ID' \
  --field resolved=true
```

Resolve only addressed Greptile discussions. Re-fetch notes and discussions,
and confirm the reviewed SHA still matches before reporting success. General
summary findings also count, even without a resolvable inline discussion.

Field definitions: [GitLab discussions API](https://docs.gitlab.com/api/discussions/).
