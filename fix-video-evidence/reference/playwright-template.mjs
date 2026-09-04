// fix-video-evidence — Playwright reproduction template.
//
// ONE script, TWO runs. The `PHASE` env var flips which final assertion runs;
// everything above the assertion block MUST stay identical between phases —
// same navigation, same clicks, same waits. Divergence is the failure mode
// this whole skill exists to catch.
//
// Usage from the target repo (invoked by the SKILL.md steps):
//   PHASE=before PR_NUM=<n> REPO_NAME=<repo> npx playwright test .videos/repro.mjs --reporter=line
//   PHASE=after  PR_NUM=<n> REPO_NAME=<repo> npx playwright test .videos/repro.mjs --reporter=line
//
// Output: .videos/<repo>-<pr>-<phase>.webm (renamed in afterAll).

import { test, expect, chromium } from '@playwright/test';
import { promises as fs } from 'node:fs';
import path from 'node:path';

const PHASE      = process.env.PHASE      || 'before';   // 'before' | 'after'
const PR_NUM     = process.env.PR_NUM     || 'local';
const REPO_NAME  = process.env.REPO_NAME  || 'repo';
const TARGET_URL = process.env.TARGET_URL || 'http://localhost:3000';   // <— set this per bug
const VIDEO_DIR  = '.videos';

let browser;
let context;
let page;

test.beforeAll(async () => {
  browser = await chromium.launch({ headless: true });
  context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: VIDEO_DIR, size: { width: 1280, height: 720 } },
    // If the app needs auth, add `storageState: '.videos/auth.json'` (a pre-baked
    // logged-in state). NEVER type real credentials on-camera.
  });
  page = await context.newPage();
});

test.afterAll(async () => {
  // Close the context FIRST so Playwright finalizes the .webm header.
  // A killed process leaves a zero-byte file — this hook is why teardown matters.
  await context?.close();
  await browser?.close();

  // Rename the auto-named .webm to the convention the attach helper greps for.
  const target = path.join(VIDEO_DIR, `${REPO_NAME}-${PR_NUM}-${PHASE}.webm`);
  const files  = (await fs.readdir(VIDEO_DIR)).filter(f => f.endsWith('.webm') && !f.includes(`${PR_NUM}-`));
  // Take the freshest untagged .webm and rename it.
  if (files.length) {
    const withStats = await Promise.all(files.map(async f => {
      const s = await fs.stat(path.join(VIDEO_DIR, f));
      return { f, mtime: s.mtimeMs };
    }));
    withStats.sort((a, b) => b.mtime - a.mtime);
    const freshest = path.join(VIDEO_DIR, withStats[0].f);
    await fs.rm(target, { force: true });
    await fs.rename(freshest, target);
    console.log(`fix-video-evidence: wrote ${target}`);
  } else {
    console.error(`fix-video-evidence: no .webm found in ${VIDEO_DIR} — did teardown run?`);
  }
});

test(`reproduce bug — phase=${PHASE}`, async () => {
  // ────────────────────────────────────────────────────────────────
  // SECTION A — reproduction flow (IDENTICAL across before/after)
  // ────────────────────────────────────────────────────────────────
  await page.goto(TARGET_URL, { waitUntil: 'networkidle' });

  // EXAMPLE steps — replace with the actual bug's flow.
  // await page.getByRole('button', { name: 'Sign in' }).click();
  // await page.getByLabel('Email').fill('demo@example.com');
  // await page.getByRole('button', { name: 'Continue' }).click();
  // await page.getByRole('link', { name: 'New shift' }).click();

  // Give the UI a beat to settle so the recording captures the state.
  await page.waitForTimeout(500);

  // ────────────────────────────────────────────────────────────────
  // SECTION B — phase-specific assertion (this is the only branch)
  // ────────────────────────────────────────────────────────────────
  if (PHASE === 'before') {
    // Assert the BUG is visible. If this fails, the reproduction is wrong —
    // fix the reproduction, not the code. A "before" video without the bug is worthless.
    // EXAMPLE:
    // await expect(page.getByText(/failed to load/i)).toBeVisible();
    // await expect(page.getByRole('button', { name: 'Save' })).toBeDisabled();
    await expect(page.locator('body')).toBeVisible();   // placeholder — replace
  } else {
    // Assert the FIX works. If this fails on the post-fix commit, the fix isn't done —
    // do NOT attach a passing-looking video.
    // EXAMPLE:
    // await expect(page.getByText(/saved/i)).toBeVisible();
    // await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
    await expect(page.locator('body')).toBeVisible();   // placeholder — replace
  }

  // Small tail so the video ends on the asserted state, not mid-transition.
  await page.waitForTimeout(500);
});
