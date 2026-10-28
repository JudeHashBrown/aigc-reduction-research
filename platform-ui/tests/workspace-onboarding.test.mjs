import assert from "node:assert/strict";
import { test } from "node:test";
import { createOnboardingStore, onboardingOwner, onboardingPage, onboardingStorageKey, workspaceTourSteps } from "../src/workspace-onboarding.js";

const session = (id) => ({ ready: true, authMode: "accounts", authenticated: true, kind: "user", user: { account_id: id } });
const memoryStorage = () => {
  const values = new Map();
  return { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
};

test("onboarding starts only for an identified authenticated account on workspace tutorial pages", () => {
  assert.equal(onboardingOwner(session("account-a")), "account-a");
  for (const invalid of [null, { ...session("a"), ready: false }, { ...session("a"), authenticated: false }, { ...session("a"), kind: "guest" }, { ...session("a"), authMode: "local" }, { ...session("a"), user: { email: "someone@example.com" } }]) {
    assert.equal(onboardingOwner(invalid), null);
  }
  assert.equal(onboardingPage("/app"), "documents");
  assert.equal(onboardingPage("/app/new"), "import");
  assert.equal(onboardingPage("/app/workbench", true), "workbench");
  assert.equal(onboardingPage("/app/workbench", false), "empty-workbench");
  for (const path of ["/auth", "/", "/checkout/pro", "/admin", "/app/billing"]) assert.equal(onboardingPage(path), null);
});

test("completion persists per account and per segment while skip dismisses future automatic segments", () => {
  const storage = memoryStorage();
  const first = createOnboardingStore(() => storage);
  assert.equal(first.shouldStart("a", "documents"), true);
  first.finish("a", "documents", "completed");
  const afterReload = createOnboardingStore(() => storage);
  assert.equal(afterReload.shouldStart("a", "documents"), false);
  assert.equal(afterReload.shouldStart("a", "workbench"), true);
  assert.equal(afterReload.shouldStart("b", "documents"), true);
  afterReload.finish("a", "import", "skipped");
  assert.equal(afterReload.shouldStart("a", "workbench"), false);
  afterReload.finish("a", "workbench", "completed");
  assert.equal(afterReload.shouldStart("a", "empty-workbench"), false);
  assert.notEqual(onboardingStorageKey("a"), onboardingStorageKey("b"));
});

test("interrupted or invalid exits never mark a tutorial completed", () => {
  const store = createOnboardingStore(() => memoryStorage());
  for (const reason of ["route-change", "logout", "missing-target", undefined]) store.finish("a", "workbench", reason);
  assert.equal(store.shouldStart("a", "workbench"), true);
});

test("storage errors and corrupt progress do not crash or cause dismissal loops", () => {
  const blocked = createOnboardingStore(() => { throw new Error("blocked"); });
  blocked.finish("a", "documents", "skipped");
  assert.equal(blocked.shouldStart("a", "workbench"), false);
  const corrupt = createOnboardingStore(() => ({ getItem: () => "{broken", setItem() { throw new Error("full"); } }));
  assert.equal(corrupt.shouldStart("b", "documents"), true);
  corrupt.finish("b", "documents", "completed");
  assert.equal(corrupt.shouldStart("b", "documents"), false);
  const stale = createOnboardingStore(() => ({ getItem: () => JSON.stringify({ version: 1, skipped: false, completed: [] }), setItem() { throw new Error("full"); } }));
  stale.finish("c", "documents", "skipped");
  assert.equal(stale.shouldStart("c", "workbench"), false);
});

test("both tutorial languages cover real targets for each segment", () => {
  for (const isEnglish of [false, true]) {
    for (const page of ["documents", "import", "workbench", "empty-workbench"]) {
      const steps = workspaceTourSteps(page, isEnglish);
      assert.ok(steps.length > 0);
      assert.equal(new Set(steps.map((item) => item.target)).size, steps.length);
      assert.ok(steps.every((item) => item.title && item.description && item.target.startsWith("[data-tour=")));
    }
  }
});
