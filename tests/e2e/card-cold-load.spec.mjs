import { expect, test } from "@playwright/test";

import { viewPath } from "./demo-personas.mjs";

// Regression guard for issue #5: the bundled card rendered as "Custom element doesn't exist:
// xplora-watch-overview-card" on every view (worst after a hard refresh). Root cause:
// `async_register_frontend_card` (custom_components/xplora_watch/helper.py) loaded the ~200KB card
// bundle via `add_extra_js_url`, which runs during early app boot -- BEFORE HA installs the
// scoped-custom-element-registry polyfill that replaces `window.customElements`. The bundle's
// `customElements.define(...)` calls then landed on the original (native) registry, which the
// polyfill swapped out, so HA looked cards up in the polyfilled registry and never found them. The
// fix registers the bundle as a storage-mode Lovelace *resource* instead -- resources load later,
// after the polyfill is in place, so the definitions land on the registry HA actually uses.
//
// This spec drives the hard case: a COLD browser context (no cached bundle, no service worker yet) --
// the hard-refresh / fresh-install scenario -- navigating straight to a card view. It asserts the
// user-facing guarantee: the `xplora-watch-overview-card` element resolves and no error card is
// shown. If registration regresses to `add_extra_js_url`, the definitions strand on the pre-polyfill
// registry and this fails at the poll. (The "resource, not add_extra_js_url" invariant is also pinned
// deterministically in the pytest suite: test_alarm_silent_helpers.py::
// test_frontend_card_registered_as_lovelace_resource_not_extra_js.)

const OVERVIEW = "xplora-watch-overview-card";

test("cold load: the overview card resolves without an error card (issue #5)", async ({ page }) => {
  await page.goto(viewPath("guardian"));

  // The custom element must resolve on this cold load (poll: the bundle loads as a deferred ES
  // module). This is the assertion that goes red if the same-realm double-load regresses: with the
  // bug, the tag stayed unregistered indefinitely, so `customElements.get(...)` never became truthy.
  await expect.poll(() => page.evaluate((tag) => !!customElements.get(tag), OVERVIEW), { timeout: 10000 }).toBeTruthy();

  // HA never swapped in its "custom element doesn't exist" error card for our tag.
  await expect(page.getByText(/custom element (doesn't exist|not found): xplora-watch-overview-card/i)).toHaveCount(0);
});
