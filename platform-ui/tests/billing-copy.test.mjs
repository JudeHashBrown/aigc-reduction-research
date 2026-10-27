import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { billableChars } from '../src/billing-text.js';
import { localizedPlanDescription, localizedPlanName } from '../src/plan-copy.js';

test('billing count treats composed and decomposed accented words alike', () => {
  assert.equal(billableChars('e\u0301 '.repeat(800)), 800);
  assert.equal(billableChars('\u00e9 '.repeat(800)), 800);
  assert.equal(billableChars('中 文\nA\t😀'), 4);
});

test('billing count removes the same hidden and variation characters as the server', () => {
  assert.equal(billableChars('甲\u200b乙\u00ad丙\u180e丁\u202e戊\u2066己\ufeff庚'), 7);
  assert.equal(billableChars('♥\ufe0f\u0000'), 1);
  assert.equal(billableChars(' \u2000\u202f\u3000'), 0);
});

test('public pricing and checkout use the same English plan copy', () => {
  const pass = { id: 'student_month', name: '学生月卡', description: '一次购买，30 天有效。' };
  assert.equal(localizedPlanName(pass, true), 'Student 30-day pass');
  assert.match(localizedPlanDescription(pass, true), /No automatic renewal/);
  assert.match(localizedPlanDescription(pass, true), /20,000 rewrite credits/);
  assert.doesNotMatch(localizedPlanDescription(pass, true), /20,000 characters/);
  assert.equal(localizedPlanName(pass, false), '学生月卡');
  assert.equal(localizedPlanDescription(pass, false), '一次购买，30 天有效。');
});

test('pricing explains the mixed-language word-credit rule', () => {
  const pricing = readFileSync(new URL('../src/pages/PublicPages.jsx', import.meta.url), 'utf8');
  assert.match(pricing, /Conservative and balanced rewrites use one credit per English word or Chinese character; deep rewrites use 1\.5×/);
  assert.match(pricing, /Numbers count as words, while punctuation and spaces do not/);
  assert.doesNotMatch(pricing, /English quota counts characters, not words|Chinese and English are measured by non-whitespace characters/);
});

test('pricing cards use direct payment labels without a Stripe caveat banner', () => {
  const pricing = readFileSync(new URL('../src/pages/PublicPages.jsx', import.meta.url), 'utf8');
  assert.match(pricing, /isEnglish \? 'Pay' : '支付'/);
  assert.doesNotMatch(pricing, /查看结账|View checkout|rtp-pricing-caveat/);
  assert.doesNotMatch(pricing, /目前尚未开放收款|Checkout is not enabled yet/);
  assert.match(pricing, /当前付款方式和可用状态以结账页为准/);
});

test('live checkout copy does not advertise the temporarily excluded wallet', () => {
  const pages = readFileSync(new URL('../src/pages/OperationsPages.jsx', import.meta.url), 'utf8');
  const liveCheckout = pages.split('export function CheckoutPage({ navigate }) {')[1]
    ?.split('function LegacyBillingPage({ navigate }) {')[0];
  assert.ok(liveCheckout);
  assert.doesNotMatch(liveCheckout, /微信支付|WeChat Pay|银行卡 \/ 微信/);
  assert.match(liveCheckout, /可用付款方式以 Stripe 收银台展示为准/);
  assert.doesNotMatch(liveCheckout, /such as card or Alipay|银行卡 \/ 支付宝等可用方式/);
});

test('credit center uses clear pricing and balance labels', () => {
  const pages = readFileSync(new URL('../src/pages/OperationsPages.jsx', import.meta.url), 'utf8');
  assert.match(pages, /title="查看额度与价格方案"/);
  assert.match(pages, /label: "价格方案"/);
  assert.match(pages, /"价格方案": "Pricing plans"/);
  assert.doesNotMatch(pages, /每一字，都有来路|平台方案/);
});

test('orders label credits accurately while historical orders retain their character-meter note', () => {
  const pages = readFileSync(new URL('../src/pages/OperationsPages.jsx', import.meta.url), 'utf8');
  assert.match(pages, /Number\(row\.metering_version \|\| 1\) < 2/);
  assert.match(pages, /legacy character meter/);
  assert.match(pages, /"billable text units"/);
  assert.doesNotMatch(pages, /"words" : "计费单位"/);
});

test('account header balance is credits, not a character count', () => {
  const app = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8');
  assert.match(app, /isEnglish \? "credits" : "额度"/);
  assert.doesNotMatch(app, /isEnglish \? "chars" : "字"/);
});
