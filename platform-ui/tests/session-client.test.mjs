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
