import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export { billableChars } from "./billing-text.js";

const PlatformContext = createContext(null);

let activeSession = {
  ready: false,
  trialMode: false,
  authMode: "unknown",
  authenticated: false,
  kind: "none",
  csrfToken: "",
  expiresAt: null,
  user: null,
  auth: {},
};
const sessionListeners = new Set();

function publishSession() {
  sessionListeners.forEach((listener) => listener({ ...activeSession }));
}

const workspace = {
  id: null,
  revision: null,
  last_job_id: null,
  name: "未命名文本",
  kind: "text",
  source: "",
  current: "",
  report: null,
  document: null,
  notices: [],
};

let activeWorkspaceOwner = null;
const WORKSPACE_STORAGE_KEY = "rightthesis-workspace";
let saveTimer = null;
let savePromise = null;
let saveStatus = { state: "saved", error: "" };
const saveListeners = new Set();

function publishSaveStatus(state, error = "") {
  saveStatus = { state, error };
  saveListeners.forEach((listener) => listener(saveStatus));
}

export function useWorkspaceSaveStatus() {
  const [status, setStatus] = useState(saveStatus);
  useEffect(() => {
    saveListeners.add(setStatus);
    return () => saveListeners.delete(setStatus);
  }, []);
  return status;
}

function storageKey(owner, id = null) {
  return `${WORKSPACE_STORAGE_KEY}:${owner}${id ? `:${id}` : ""}`;
}
function activeKey(owner) { return `${WORKSPACE_STORAGE_KEY}-active:${owner}`; }

function localSnapshot(dirty) {
  return {
    owner: activeWorkspaceOwner, id: workspace.id, revision: workspace.revision,
    name: workspace.name, kind: workspace.kind, source: workspace.source,
    current: workspace.current, report: workspace.id ? null : workspace.report,
    notices: workspace.notices,
    last_job_id: workspace.last_job_id, dirty,
  };
}

function writeLocalBackup(dirty = true) {
  if (!activeWorkspaceOwner || !workspace.source) return false;
  try {
    window.localStorage.setItem(storageKey(activeWorkspaceOwner, workspace.id), JSON.stringify(localSnapshot(dirty)));
    if (workspace.id) window.localStorage.setItem(activeKey(activeWorkspaceOwner), workspace.id);
    return true;
  } catch {
    publishSaveStatus("error", "浏览器本地备份失败；请立即下载当前稿。");
    return false;
  }
}

function workspaceOwnerFor(session) {
  if (!session?.ready) return null;
  if (session.authMode === "accounts") {
    if (!session.authenticated) return null;
    const accountId = session.user?.account_id || session.user?.id;
    return accountId ? `account:${accountId}` : null;
  }
  if (session.trialMode || session.kind === "guest") {
    const accountId = session.user?.account_id || session.user?.id;
    return accountId ? `guest:${accountId}` : null;
  }
  return session.authMode === "local" ? "local" : null;
}

function resetWorkspaceMemory() {
  Object.assign(workspace, {
    id: null,
    revision: null,
    last_job_id: null,
    name: "未命名文本",
    kind: "text",
    source: "",
    current: "",
    report: null,
    document: null,
    notices: [],
  });
}

export function clearWorkspace(removeLocal = false) {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = null;
  const priorOwner = activeWorkspaceOwner;
  resetWorkspaceMemory();
  activeWorkspaceOwner = null;
  if (typeof window !== "undefined") {
    try {
      if (removeLocal) window.sessionStorage.removeItem(WORKSPACE_STORAGE_KEY);
      if (removeLocal && priorOwner) {
        const prefix = `${WORKSPACE_STORAGE_KEY}:${priorOwner}`;
        const retained = [];
        for (let index = window.localStorage.length - 1; index >= 0; index -= 1) {
          const key = window.localStorage.key(index);
          if (key === prefix || key?.startsWith(`${prefix}:`)) {
            let cached = null;
            try { cached = JSON.parse(window.localStorage.getItem(key) || "null"); } catch { /* remove corrupt cache */ }
            if (cached?.dirty && cached?.id) retained.push(cached.id);
            else window.localStorage.removeItem(key);
          }
        }
        if (retained.length) window.localStorage.setItem(activeKey(priorOwner), retained[0]);
        else window.localStorage.removeItem(activeKey(priorOwner));
      }
    } catch {
      // The in-memory workspace is still cleared when storage is unavailable.
    }
  }
  publishSaveStatus("saved");
  return workspace;
}

function applySession(payload = {}) {
  const next = payload && typeof payload.session === "object" ? payload.session : payload;
  const authEnvelope = (next.auth && typeof next.auth === "object" && next.auth) || {};
  const providerSource = (authEnvelope.providers && typeof authEnvelope.providers === "object" && authEnvelope.providers)
    || (next.providers && typeof next.providers === "object" && next.providers)
    || (payload.providers && typeof payload.providers === "object" && payload.providers)
    || {};
  const emailProvider = providerSource.email_password ?? providerSource.email ?? providerSource.email_code;
  const googleProvider = providerSource.google;
  const auth = {
    ...authEnvelope,
    ...providerSource,
    email_enabled: Boolean(providerSource.email_enabled
      ?? (typeof emailProvider === "object" ? emailProvider.enabled : emailProvider)),
    google_enabled: Boolean(providerSource.google_enabled
      ?? (typeof googleProvider === "object" ? googleProvider.enabled : googleProvider)),
    google_configured: Boolean(providerSource.google_configured
      ?? (typeof googleProvider === "object" ? googleProvider.configured : googleProvider)),
    email_delivery: authEnvelope.email_delivery
      || providerSource.email_delivery
      || (typeof emailProvider === "object" ? emailProvider.delivery : "")
      || "",
  };
  const authMode = next.auth_mode || payload.auth_mode || (next.trial_mode ? "trial" : "local");
  activeSession = {
    ready: true,
    trialMode: Boolean(next.trial_mode),
    authMode,
    authenticated: Boolean(next.authenticated),
    kind: next.kind || next.user?.kind || (next.authenticated ? "user" : "none"),
    csrfToken: next.csrf_token || "",
    expiresAt: next.expires_at || null,
    user: next.user || null,
    auth,
  };
  publishSession();
  return activeSession;
}

async function parseResponse(response) {
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    // A non-JSON response is still reported with the HTTP status below.
  }
  if (!response.ok) {
    const error = new Error(payload?.error || `请求失败（HTTP ${response.status}）`);
    error.status = response.status;
    error.data = payload;
    throw error;
  }
  return payload || {};
}

export async function ensureSession(force = false) {
  if (activeSession.ready && !force) return activeSession;
  const response = await fetch("/api/session", {
    cache: "no-store",
    credentials: "same-origin",
  });
  const payload = await parseResponse(response);
  return applySession(payload);
}

async function refreshAccountAfterUnauthorized() {
  if (activeSession.authMode !== "accounts") return;
  try {
    await ensureSession(true);
  } catch {
    // The API has already returned 401. Keep local drafts, but close access
    // to protected screens even if the session-status request also fails.
    activeSession = { ...activeSession, authenticated: false, kind: "none", csrfToken: "", user: null };
    publishSession();
  }
}

export async function getApi(path, retry = true) {
  await ensureSession();
  const response = await fetch(path, {
    cache: "no-store",
    credentials: "same-origin",
  });
  try {
    return await parseResponse(response);
  } catch (error) {
    if (error.status === 401 && activeSession.trialMode && retry) {
      await ensureSession(true);
      return getApi(path, false);
    }
    if (error.status === 401) await refreshAccountAfterUnauthorized();
    throw error;
  }
}

export async function postApi(path, body, retry = true) {
  await ensureSession();
  const headers = { "Content-Type": "application/json" };
  if (activeSession.csrfToken) headers["X-CSRF-Token"] = activeSession.csrfToken;
  const response = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers,
    body: JSON.stringify(body),
  });
  try {
    return await parseResponse(response);
  } catch (error) {
    if (error.status === 401 && activeSession.trialMode && retry) {
      await ensureSession(true);
      return postApi(path, body, false);
    }
    if (error.status === 401) await refreshAccountAfterUnauthorized();
    throw error;
  }
}

function safeReturnPath(value) {
  const path = typeof value === "string" ? value.trim() : "";
  if (!path.startsWith("/") || path.startsWith("//") || path.includes("://")) return "/app";
  return path;
}

export async function registerAccount(email, password, displayName) {
  return postApi("/api/auth/register", {
    email: String(email || "").trim(),
    password: String(password || ""),
    display_name: String(displayName || "").trim(),
  });
}

export async function verifyRegistration(challengeId, code) {
  return postApi("/api/auth/register/verify", {
    challenge_id: String(challengeId || ""),
    code: String(code || ""),
  });
}

export async function resendRegistration(challengeId) {
  return postApi("/api/auth/register/resend", {
    challenge_id: String(challengeId || ""),
  });
}

export async function loginWithEmail(email, password) {
  return postApi("/api/auth/login", {
    email: String(email || "").trim(),
    password: String(password || ""),
  });
}

export async function requestPasswordReset(email) {
  return postApi("/api/auth/password/forgot", {
    email: String(email || "").trim(),
  });
}

export async function resetPassword(challengeId, code, newPassword) {
  return postApi("/api/auth/password/reset", {
    challenge_id: String(challengeId || ""),
    code: String(code || ""),
    new_password: String(newPassword || ""),
  });
}

export function beginGoogleLogin(returnTo = "/app") {
  const query = new URLSearchParams({ return_to: safeReturnPath(returnTo) });
  window.location.assign(`/api/auth/google/start?${query.toString()}`);
}

export async function logoutSession({ skipSave = false } = {}) {
  if (!skipSave && workspace.id && saveStatus.state !== "saved") {
    try { await saveWorkspaceNow(); }
    catch (error) { error.unsavedDraft = true; throw error; }
  }
  await postApi("/api/auth/logout", {});
  clearWorkspace(true);
  if (typeof window !== "undefined") {
    try {
      window.sessionStorage.removeItem("rightthesis-register-verification");
      window.sessionStorage.removeItem("rightthesis-password-reset");
      window.sessionStorage.removeItem("rightthesis-auth-return");
    } catch {
      // The server session is already revoked; storage cleanup is best effort.
    }
  }
  return ensureSession(true);
}

export function getWorkspace() {
  return workspace;
}

export function getUnsavedLocalBackup() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(storageKey(activeWorkspaceOwner, workspace.id)) || "null");
    return saved?.owner === activeWorkspaceOwner && saved?.dirty ? saved.current : null;
  } catch { return null; }
}

export function downloadUnsavedDraftBackup() {
  if (typeof window === "undefined" || typeof document === "undefined") return false;
  const owner = activeWorkspaceOwner || workspaceOwnerFor(activeSession);
  if (!owner) return false;
  const drafts = [];
  const prefix = `${WORKSPACE_STORAGE_KEY}:${owner}:`;
  try {
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index);
      if (!key?.startsWith(prefix)) continue;
      const saved = JSON.parse(window.localStorage.getItem(key) || "null");
      if (saved?.owner === owner && saved?.dirty) drafts.push(saved);
    }
    if (workspace.id && saveStatus.state !== "saved"
        && !drafts.some((draft) => draft.id === workspace.id)) {
      drafts.push({ ...workspace, owner, dirty: true });
    }
    if (!drafts.length) return false;
    const blob = new Blob([JSON.stringify({ format: "rightthesis-unsaved-v1", drafts }, null, 2)],
      { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `rightthesis-unsaved-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    return true;
  } catch { return false; }
}

export function getUnsavedDrafts() {
  const owner = workspaceOwnerFor(activeSession);
  if (!owner) return [];
  const prefix = `${WORKSPACE_STORAGE_KEY}:${owner}:`;
  const drafts = [];
  try {
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index);
      if (!key?.startsWith(prefix)) continue;
      const saved = JSON.parse(window.localStorage.getItem(key) || "null");
      if (saved?.owner === owner && saved?.dirty && saved?.id) {
        drafts.push({ id: saved.id, name: saved.name || saved.id });
      }
    }
  } catch { /* A broken backup cannot be listed. */ }
  return drafts;
}

export function updateWorkspace(next) {
  Object.assign(workspace, next);
  if (typeof window !== "undefined") {
    const owner = workspaceOwnerFor(activeSession);
    if (!owner) return workspace;
    activeWorkspaceOwner = owner;
    const backedUp = writeLocalBackup(true);
    if (workspace.id) {
      if (backedUp) publishSaveStatus("saving");
      if (saveTimer) clearTimeout(saveTimer);
      saveTimer = setTimeout(() => { saveWorkspaceNow().catch(() => null); }, 600);
    }
  }
  return workspace;
}

export function restoreWorkspace(session = activeSession) {
  const owner = workspaceOwnerFor(session);
  const ownerChanged = activeWorkspaceOwner !== owner;
  if (ownerChanged) resetWorkspaceMemory();
  activeWorkspaceOwner = owner;
  if (!ownerChanged && workspace.id) return workspace;
  try {
    const activeId = owner && window.localStorage.getItem(activeKey(owner));
    const saved = owner && JSON.parse(window.localStorage.getItem(storageKey(owner, activeId))
      || window.localStorage.getItem(storageKey(owner)) || "null");
    const legacyLocal = owner === "local" && saved && !saved.owner;
    if (owner && saved && (saved.owner === owner || legacyLocal) && typeof saved.source === "string") {
      Object.assign(workspace, saved);
    } else if (owner && !workspace.source) {
      const legacy = JSON.parse(window.sessionStorage.getItem(WORKSPACE_STORAGE_KEY) || "null");
      if (legacy?.source && (legacy.owner === owner || (owner === "local" && !legacy.owner))) {
        Object.assign(workspace, legacy);
      }
    }
  } catch {
    // A corrupt browser cache never overwrites the server's saved document.
  }
  return workspace;
}

export async function saveWorkspaceNow() {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = null;
  if (savePromise) {
    await savePromise;
    if (saveStatus.state !== "saving") return workspace;
  }
  const owner = activeWorkspaceOwner;
  if (!owner || !workspace.id || !workspace.revision) return workspace;
  const snapshot = {
    id: workspace.id, revision: workspace.revision, current: workspace.current,
    report: workspace.report, notices: workspace.notices, last_job_id: workspace.last_job_id,
  };
  publishSaveStatus("saving");
  savePromise = postApi(`/api/documents/${encodeURIComponent(snapshot.id)}/save`, snapshot)
    .then(({ document }) => {
      if (activeWorkspaceOwner !== owner || workspace.id !== snapshot.id) return;
      workspace.revision = document.revision;
      if (workspace.current === snapshot.current && workspace.report === snapshot.report) {
        writeLocalBackup(false);
        publishSaveStatus("saved");
      } else {
        writeLocalBackup(true);
        publishSaveStatus("saving");
      }
    })
    .catch((error) => {
      publishSaveStatus("error", error.message || "服务端保存失败，请下载本地副本。");
      throw error;
    })
    .finally(() => { savePromise = null; });
  await savePromise;
  if (saveStatus.state === "saving" && activeWorkspaceOwner === owner) return saveWorkspaceNow();
  return workspace;
}

export async function createWorkspace(value) {
  await ensureSession();
  if (workspace.id && saveStatus.state !== "saved") await saveWorkspaceNow();
  const owner = workspaceOwnerFor(activeSession);
  if (!owner) throw new Error("请先登录后保存文稿。");
  const { document } = await postApi("/api/documents", value);
  if (saveTimer) clearTimeout(saveTimer);
  resetWorkspaceMemory();
  activeWorkspaceOwner = owner;
  Object.assign(workspace, document);
  writeLocalBackup(false);
  publishSaveStatus("saved");
  return workspace;
}

export async function openWorkspace(id) {
  try { await saveWorkspaceNow(); }
  catch (error) { if (!getUnsavedLocalBackup()) throw error; }
  const { document } = await getApi(`/api/documents/${encodeURIComponent(id)}`);
  resetWorkspaceMemory();
  activeWorkspaceOwner = workspaceOwnerFor(activeSession);
  Object.assign(workspace, document);
  let cached = null;
  try { cached = JSON.parse(window.localStorage.getItem(storageKey(activeWorkspaceOwner, id)) || "null"); }
  catch { /* The server copy is still available. */ }
  if (cached?.dirty && cached.revision === document.revision) {
    workspace.current = cached.current;
    workspace.report = cached.report;
    workspace.notices = cached.notices;
    writeLocalBackup(true);
    publishSaveStatus("saving");
    await saveWorkspaceNow();
  } else if (cached?.dirty) {
    publishSaveStatus("error", "本机未同步稿与服务器版本冲突；请先下载未同步备份。");
  } else {
    writeLocalBackup(false);
    publishSaveStatus("saved");
  }
  return workspace;
}

async function hydrateWorkspace(session) {
  const owner = workspaceOwnerFor(session);
  if (!owner) { clearWorkspace(); return; }
  if (owner === activeWorkspaceOwner && workspace.id && saveStatus.state === "saving") {
    await saveWorkspaceNow().catch(() => null);
  }
  const cachedMemory = { ...restoreWorkspace(session) };
  let cachedBackup = null;
  try { cachedBackup = JSON.parse(window.localStorage.getItem(storageKey(owner, cachedMemory.id))
    || window.localStorage.getItem(storageKey(owner)) || "null"); }
  catch { /* The server copy remains authoritative. */ }
  const cached = { ...cachedMemory, ...(cachedBackup?.owner === owner ? cachedBackup : {}) };
  if (cached.source && !cached.id) {
    // The previous release retained text but never stored original file bytes.
    await createWorkspace({
      name: `${cached.name || "未命名文稿"}（恢复文本）`, kind: "text",
      source: cached.source, current: cached.current || cached.source,
      report: cached.report || null, notices: [
        ...(cached.notices || []),
        { level: "warn", text: "已恢复旧工作区文字；旧版未保存原始文件，若需保留 DOCX 格式请重新导入。" },
      ],
    });
    try { window.sessionStorage.removeItem(WORKSPACE_STORAGE_KEY); } catch { /* no-op */ }
    return;
  }
  const listing = await getApi("/api/documents");
  const targetId = cached.id || listing.documents?.[0]?.id;
  if (targetId) {
    try {
      const { document } = await getApi(`/api/documents/${encodeURIComponent(targetId)}`);
      resetWorkspaceMemory();
      Object.assign(workspace, document);
      if (cached.dirty && cached.id === document.id && cached.revision === document.revision) {
        workspace.current = cached.current;
        workspace.report = cached.report;
        workspace.notices = cached.notices;
        writeLocalBackup(true);
        publishSaveStatus("saving");
        saveWorkspaceNow().catch(() => null);
      } else if (cached.dirty && cached.id === document.id && cached.revision !== document.revision) {
        publishSaveStatus("error", "另一页面已更新文稿；本机未同步稿仍保留在浏览器缓存，请先下载备份。");
      } else {
        writeLocalBackup(false);
        publishSaveStatus("saved");
      }
      return;
    } catch (error) {
      if (error.status !== 404) throw error;
    }
  }
}

export function requestId(prefix = "request") {
  if (globalThis.crypto?.randomUUID) return `${prefix}_${crypto.randomUUID().replaceAll("-", "")}`;
  return `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
}

export async function fileToBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  const chunk = 0x8000;
  for (let index = 0; index < bytes.length; index += chunk) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunk));
  }
  return btoa(binary);
}

export function downloadBase64(file, mimeType, fileName) {
  const binary = atob(file);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  const url = URL.createObjectURL(new Blob([bytes], { type: mimeType }));
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function PlatformProvider({ children }) {
  const [session, setSession] = useState(activeSession);
  const [config, setConfig] = useState(null);
  const [billing, setBilling] = useState(null);
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    sessionListeners.add(setSession);
    return () => sessionListeners.delete(setSession);
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const nextSession = await ensureSession(true);
      setSession({ ...nextSession });
      const shouldLoadAccountData = nextSession.authMode !== "accounts" || nextSession.authenticated;
      if (shouldLoadAccountData) await hydrateWorkspace(nextSession);
      else clearWorkspace();
      const [configResult, plansResult, billingResult] = await Promise.allSettled([
        getApi("/api/config"),
        getApi("/api/billing/plans"),
        shouldLoadAccountData ? getApi("/api/billing/summary") : Promise.resolve(null),
      ]);
      if (configResult.status === "fulfilled") setConfig(configResult.value);
      if (plansResult.status === "fulfilled") setPlans(plansResult.value.plans || []);
      if (billingResult.status === "fulfilled") setBilling(billingResult.value);
      if (!shouldLoadAccountData) setBilling(null);
      const expectedResults = shouldLoadAccountData
        ? [configResult, plansResult, billingResult]
        : [configResult, plansResult];
      const failed = expectedResults.find((item) => item.status === "rejected");
      if (failed) setError(failed.reason?.message || "部分平台状态暂时不可用");
    } catch (nextError) {
      setError(nextError.message || "无法连接 RightThesis 服务");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const onBeforeUnload = (event) => {
      if (saveStatus.state === "saved") return;
      event.preventDefault();
      event.returnValue = "";
    };
    const onVisibility = () => {
      if (document.visibilityState === "hidden" && saveStatus.state === "saving") {
        saveWorkspaceNow().catch(() => null);
      }
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  const refreshBilling = useCallback(async () => {
    const next = await getApi("/api/billing/summary");
    setBilling(next);
    return next;
  }, []);

  const value = useMemo(() => ({
    session,
    config,
    billing,
    plans,
    loading,
    error,
    refresh,
    refreshBilling,
    setBilling,
  }), [session, config, billing, plans, loading, error, refresh, refreshBilling]);

  return <PlatformContext.Provider value={value}>{children}</PlatformContext.Provider>;
}

export function usePlatform() {
  const context = useContext(PlatformContext);
  if (!context) throw new Error("usePlatform must be used inside PlatformProvider");
  return context;
}

export function useOptionalPlatform() {
  return useContext(PlatformContext);
}
