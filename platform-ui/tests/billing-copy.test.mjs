import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { billableChars } from '../src/billing-text.js';
import { localizedPlanDescription, localizedPlanName } from '../src/plan-copy.js';

test('billing count preserves decomposed characters like the server', () => {
  assert.equal(billableChars('e\u0301'.repeat(800)), 1600);
  assert.equal(billableChars('\u00e9'.repeat(800)), 800);
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
  assert.equal(localizedPlanName(pass, false), '学生月卡');
  assert.equal(localizedPlanDescription(pass, false), '一次购买，30 天有效。');
});

test('pricing cards use direct payment labels without a Stripe caveat banner', () => {
  const pricing = readFileSync(new URL('../src/pages/PublicPages.jsx', import.meta.url), 'utf8');
  assert.match(pricing, /isEnglish \? 'Pay' : '支付'/);
  assert.doesNotMatch(pricing, /查看结账|View checkout|rtp-pricing-caveat/);
});
