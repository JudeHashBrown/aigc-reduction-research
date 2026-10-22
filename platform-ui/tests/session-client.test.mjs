import assert from 'node:assert/strict';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

test('an account API 401 refreshes cached authentication state', async () => {
  const output = await build({
    entryPoints: [fileURLToPath(new URL('../src/platform.jsx', import.meta.url))],
    bundle: true,
    format: 'esm',
    platform: 'node',
    jsx: 'automatic',
    write: false,
    logLevel: 'silent',
  });
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(output.outputFiles[0].text).toString('base64')}`;
  const client = await import(moduleUrl);
  const originalFetch = globalThis.fetch;
  let sessionReads = 0;
  globalThis.fetch = async (url) => {
    if (url === '/api/session') {
      sessionReads += 1;
      const authenticated = sessionReads === 1;
      return new Response(JSON.stringify({
        auth_mode: 'accounts', authenticated,
        kind: authenticated ? 'user' : 'none',
        user: authenticated ? { id: 'user-1' } : null,
        csrf_token: authenticated ? 'csrf-test' : '',
      }), { status: 200, headers: { 'content-type': 'application/json' } });
    }
    assert.equal(url, '/api/private');
    return new Response(JSON.stringify({ error: 'Session expired' }), {
      status: 401, headers: { 'content-type': 'application/json' },
    });
  };
  try {
    assert.equal((await client.ensureSession(true)).authenticated, true);
    await assert.rejects(client.getApi('/api/private'), (error) => error.status === 401);
    assert.equal((await client.ensureSession()).authenticated, false);
    assert.equal(sessionReads, 2);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('a failed draft save offers a downloadable backup before forced sign-out', async () => {
  const output = await build({
    entryPoints: [fileURLToPath(new URL('../src/platform.jsx', import.meta.url))],
    bundle: true, format: 'esm', platform: 'node', jsx: 'automatic', write: false, logLevel: 'silent',
  });
  const client = await import(`data:text/javascript;base64,${Buffer.from(output.outputFiles[0].text).toString('base64')}#draft-test`);
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  const originalCreateObjectURL = URL.createObjectURL;
  const originalRevokeObjectURL = URL.revokeObjectURL;
  const entries = new Map();
  const storage = {
    get length() { return entries.size; },
    key(index) { return [...entries.keys()][index] || null; },
    getItem(key) { return entries.get(key) ?? null; },
    setItem(key, value) { entries.set(key, value); },
    removeItem(key) { entries.delete(key); },
  };
  let logoutCalls = 0;
  let downloads = 0;
  globalThis.window = {
    localStorage: storage, sessionStorage: storage,
    setTimeout(fn, delay) { const timer = setTimeout(fn, delay); timer.unref(); return timer; },
  };
  globalThis.document = {
    body: { appendChild() {} },
    createElement() { return { click() { downloads += 1; }, remove() {} }; },
  };
  URL.createObjectURL = () => 'blob:backup';
  URL.revokeObjectURL = () => {};
  globalThis.fetch = async (url) => {
    if (url === '/api/session') return new Response(JSON.stringify({
      auth_mode: 'accounts', authenticated: logoutCalls === 0,
      kind: logoutCalls === 0 ? 'user' : 'none',
      user: logoutCalls === 0 ? { id: 'buyer' } : null,
      csrf_token: logoutCalls === 0 ? 'csrf-test' : '',
    }), { status: 200 });
    if (url === '/api/documents/doc-1/save') {
      return new Response(JSON.stringify({ error: 'Save unavailable' }), { status: 503 });
    }
    if (url === '/api/auth/logout') {
      logoutCalls += 1;
      return new Response('{}', { status: 200 });
    }
    throw new Error(`unexpected request: ${url}`);
  };
  try {
    await client.ensureSession(true);
    client.updateWorkspace({ id: 'doc-1', revision: 1, source: 'original', current: 'unsaved edit' });
    await assert.rejects(client.logoutSession(), (error) => error.unsavedDraft === true);
    assert.equal(logoutCalls, 0);
    assert.equal(client.getUnsavedLocalBackup(), 'unsaved edit');
    assert.equal(client.downloadUnsavedDraftBackup(), true);
    assert.equal(downloads, 1);
    await client.logoutSession({ skipSave: true });
    assert.equal(logoutCalls, 1);
    assert.equal([...entries.values()].some((value) => value.includes('unsaved edit')), true);
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.window = originalWindow;
    globalThis.document = originalDocument;
    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
  }
});
