# Perforce reviews

Use this path only when the task targets Perforce. An installed or authenticated
`p4` executable alone does not identify the current project as a Perforce task.

Confirm the client, user, pending changelist, and shelved files with `p4 info`,
`p4 changes`, and `p4 describe -S CL`. Preserve other tasks' workspaces and files.
Run relevant checks before updating the requested shelf with `p4 shelve -f -c CL`.

Use the site's configured Greptile or Swarm integration to trigger review.
Record the shelf revision or content digest, trigger time, and review attempt
identifier. Poll that attempt with a 10-minute deadline and check the shelf
identity again before accepting feedback. A changelist number alone does not
identify a shelf revision. Do not reuse an older score after re-shelving.

Fetch all pages of bot feedback through the site's configured review API. Read
summary findings and unresolved inline discussions. Apply the shared workflow's
rules for fixes, checks, publication, and resolution. Re-shelving starts a new
review cycle and counts toward the same iteration cap.

Perforce review APIs and trigger mechanisms vary by installation. If the task
context does not identify the adapter or it cannot prove which shelf was
reviewed, report the missing configuration and stop. Do not guess an endpoint,
post to an unrelated integration, or claim the latest changelist was reviewed.
