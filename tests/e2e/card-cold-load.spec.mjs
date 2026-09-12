import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { expect, test } from "@playwright/test";

import { viewPath } from "./demo-personas.mjs";

// Deterministic reproduction of issue #5: the bundled card renders as "Custom element doesn't exist:
// xplora-watch-overview-card" on a cold load. Root cause (confirmed against HA frontend source, tag
// 20260624.4): the Lovelace panel loads card resources FIRE-AND-FORGET (ha-panel-lovelace.ts calls
// loadLovelaceResources, not ...AndWait) and renders views without awaiting them; an undefined
// hyphenated custom element gets a hui-error-card that is hidden for only 2s (create-element-base.ts
// TIMEOUT) before it becomes visible. So if the ~200KB card bundle hasn't executed its
// customElements.define() calls within that window of the dashboard rendering, the user sees the
// error card. A hard refresh (cold service-worker cache) is the worst case.
//
// This test forces that window deterministically by delaying ONLY the heavy bundle
// (xplora-watch-card.js). A fresh browser context has no service worker yet, so the request hits the
// network and the route delay applies. It asserts the DESIRED post-fix behaviour: the custom element
// is defined promptly (so HA never shows the error card) even though the heavy bundle is slow --
// which is only possible if a tiny separate loader module defines the elements up front and
// lazy-loads the heavy implementation.
//
// Marked test.fail() because it documents a known-open bug: on today's code the ONLY definer is the
// delayed heavy bundle, so the element stays undefined past the window and this assertion fails
// (keeping CI green). The fix (a lightweight loader that registers the tags immediately) removes the
// test.fail() marker.

const OVERVIEW = "xplora-watch-overview-card";
// Matches the heavy bundle at both URLs it is served from -- the plain add_extra_js_url path and the
// versioned Lovelace resource (…card.js?v=…) -- but NOT a separate …card-loader.js.
const HEAVY_BUNDLE = /xplora-watch-card\.js(\?|$)/;
const STORAGE_STATE = resolve(dirname(fileURLToPath(import.meta.url)), "../../.e2e-ha/storage-state.json");
const BUNDLE_DELAY_MS = 5000;

test.fail(); // Known-open (issue #5); the loader fix removes this line.
test("cold load: the overview card is defined before render even when the heavy bundle is slow", async ({ browser }) => {
  const context = await browser.newContext({ storageState: STORAGE_STATE });
  const page = await context.newPage();

  await context.route(HEAVY_BUNDLE, async (route) => {
    await new Promise((r) => setTimeout(r, BUNDLE_DELAY_MS));
    await route.continue();
  });

  await page.goto(viewPath("guardian"), { waitUntil: "domcontentloaded" });

  // The element must resolve well within HA's 2s error-card window -- proof the tag is registered by
  // something lighter than the delayed heavy bundle. Poll briefly (not the full 20s expect timeout).
  await expect
    .poll(() => page.evaluate((tag) => !!customElements.get(tag), OVERVIEW), { timeout: 2000, intervals: [100] })
    .toBeTruthy();

  // And HA never swapped in its "custom element doesn't exist" error card for our tag.
  await expect(page.getByText(/custom element (doesn't exist|not found): xplora-watch-overview-card/i)).toHaveCount(0);

  await context.close();
});
