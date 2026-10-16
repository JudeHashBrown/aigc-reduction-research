#!/usr/bin/env node
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import react from '@vitejs/plugin-react';
import { createServer } from 'vite';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dist = path.join(root, 'dist', 'client');
const template = await readFile(path.join(dist, 'index.html'), 'utf8');
const mount = '<div id="root"></div>';
if (!template.includes(mount)) throw new Error('Built frontend mount point not found');

// Use the same React components as the browser. The browser still mounts a
// fresh interactive app, while crawlers can read homepage links and policies
// without executing JavaScript.
const vite = await createServer({
  root,
  configFile: false,
  plugins: [react()],
  server: { middlewareMode: true, hmr: false },
  appType: 'custom',
});

try {
  const { LocaleProvider } = await vite.ssrLoadModule('/src/locale.jsx');
  const { PlatformProvider } = await vite.ssrLoadModule('/src/platform.jsx');
  const { LandingPage, PrivacyPage, TermsPage } = await vite.ssrLoadModule('/src/pages/PublicPages.jsx');
  const pages = [
    { route: '/', component: LandingPage, title: 'RightThesis · 学术表达检测与保真改写' },
    { route: '/legal/privacy', component: PrivacyPage, title: '隐私政策 · RightThesis' },
    { route: '/legal/terms', component: TermsPage, title: '服务条款 · RightThesis' },
  ];

  for (const { route, component, title } of pages) {
    const page = React.createElement(component, { navigate: () => {} });
    const withPlatform = route === '/' ? React.createElement(PlatformProvider, null, page) : page;
    const markup = renderToStaticMarkup(React.createElement(LocaleProvider, null, withPlatform));
    const html = template
      .replace(mount, `<div id="root">${markup}</div>`)
      .replace(/<title>[^<]*<\/title>/, `<title>${title}</title>`);
    const destination = route === '/' ? path.join(dist, 'index.html') : path.join(dist, route, 'index.html');
    await mkdir(path.dirname(destination), { recursive: true });
    await writeFile(destination, html, 'utf8');
    console.log(`Prerendered ${route}: ${markup.length} characters`);
  }
} finally {
  await vite.close();
}
