---
name: greploop-apps
description: Run the greploop workflow with the @greptile-apps trigger when the normal trigger refuses a large PR. Requires the greploop skill installed alongside this entrypoint.
license: MIT
metadata:
  author: greptileai
  version: "2.0"
---

# Greploop apps

This is a compatibility entrypoint for `/greploop --trigger @greptile-apps`.
Read the installed `greploop` skill and follow its workflow with that trigger.
Preserve the user's target, iteration cap, task scope, and existing authorization.

In this collection the shared workflow is [greploop](../greploop/SKILL.md).
If installed separately, locate `greploop` in the environment's skill catalog.
If it is missing, report the dependency and provide the paired installation
command below. Do not invent a second workflow or install dependencies without
an installation request.

```bash
cp -r greploop greploop-apps ~/.claude/skills/
```

All polling, freshness checks, platform references, and stopping conditions
belong to `greploop`. This entrypoint contains no separate implementation.
