import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { expect, test } from "@playwright/test";

import { viewPath } from "./demo-personas.mjs";

// Browser e2e for the card's registration -- the "Custom element doesn't exist:
// xplora-watch-overview-card" error users hit (issue #5). The integration registers the bundle as a
// storage-mode Lovelace *resource* (loaded after HA's scoped-custom-element-registry polyfill is in
// place), deliberately NOT via `add_extra_js_url` -- which loads too early, so the card's
// `customElements.define(...)` calls would land on the native registry the polyfill then replaces,
// leaving HA unable to find the tags. Demo account only, never a real login (ADR 0009).
//
// What this spec proves (the observable outcome of the fix): the `xplora-watch-overview-card`
// element resolves in the registry HA uses and its dashboard view renders the card rather than HA's
// "custom element doesn't exist" error card.
//
// The cold-load regression guard lives in tests/e2e/card-cold-load.spec.mjs. The "resource, not
// add_extra_js_url" invariant is pinned deterministically in the pytest suite
// (tests/xplora_watch/helper/test_alarm_silent_helpers.py::
// test_frontend_card_registered_as_lovelace_resource_not_extra_js).
//
// One warm, authenticated page is shared across the file (serial), mirroring map-card.spec.mjs: the
// HA frontend compiles once (cold, it is slow) and each spec drives client-side navigation from
// there. The storageState written by global-setup.mjs makes the page already authenticated.

const OVERVIEW = "xplora-watch-overview-card";
const STORAGE_STATE = resolve(dirname(fileURLToPath(import.meta.url)), "../../.e2e-ha/storage-state.json");

test.describe.configure({ mode: "serial" });

/** @type {import('@playwright/test').BrowserContext} */
let context;
/** @type {import('@playwright/test').Page} */
let page;

test.beforeAll(async ({ browser }) => {
  context = await browser.newContext({ storageState: STORAGE_STATE });
  page = await context.newPage();
  // Warm the frontend once (the cold compile is the slow part) and confirm we're authenticated.
  await page.goto("/");
  await expect(page.locator("home-assistant")).toBeAttached();
});

test.afterAll(async () => {
  await context?.close();
});

test('overview card resolves and renders (no "custom element doesn\'t exist")', async () => {
  await page.goto(viewPath("guardian"));
  const card = page.locator(OVERVIEW).first();
  await expect(card).toBeAttached();

  // The custom element is actually defined in the registry -- the thing that is missing during the
  // race. Poll: the bundle loads as a deferred module, so the definition can land just after attach.
  await expect.poll(() => page.evaluate((tag) => !!customElements.get(tag), OVERVIEW)).toBeTruthy();

  // The card mounted its own content (a row) rather than HA swapping in an error card for this tag.
  await expect(card.locator(".row").first()).toBeVisible();
  await expect(page.getByText(/custom element (doesn't exist|not found): xplora-watch-overview-card/i)).toHaveCount(0);
});
