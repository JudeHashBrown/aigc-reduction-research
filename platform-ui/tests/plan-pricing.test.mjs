import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { catalogQuote, formatQuote, orderQuote, preferredPriceCurrency } from '../src/plan-pricing.js';

const student = {
  id: 'student_month', kind: 'subscription', price_fen: 3990, currency: 'CNY',
  prices: { CNY: { amount_minor: 3990, currency: 'CNY' }, USD: { amount_minor: 790, currency: 'USD' } },
};

test('English and Chinese offers use explicit server prices, not an exchange-rate conversion', () => {
  assert.equal(preferredPriceCurrency(true), 'USD');
  assert.equal(preferredPriceCurrency(false), 'CNY');
  assert.equal(formatQuote(catalogQuote(student, 'USD'), true, true), '$7.90 USD');
  assert.equal(formatQuote(catalogQuote(student, 'CNY'), false, true), '¥39.90 CNY');
});

test('missing or malformed USD quotes fail closed instead of displaying a CNY amount as USD', () => {
  assert.equal(catalogQuote({ ...student, prices: undefined }, 'USD'), null);
  assert.equal(catalogQuote({ ...student, prices: { USD: { amount_minor: 790, currency: 'CNY' } } }, 'USD'), null);
  assert.equal(catalogQuote({ ...student, prices: { USD: { amount_minor: 0, currency: 'USD' } } }, 'USD'), null);
  assert.equal(catalogQuote({ ...student, prices: undefined }, 'CNY')?.amount_minor, 3990);
});

test('historical order amounts remain in their actual purchased currency regardless of UI language', () => {
  const cnyOrder = { amount_fen: 3990, currency: 'CNY' };
  const usdOrder = { amount_minor: 790, amount_fen: 790, currency: 'USD' };
  assert.equal(formatQuote(orderQuote(cnyOrder), true, true), '¥39.90 CNY');
  assert.equal(formatQuote(orderQuote(usdOrder), false, true), '$7.90 USD');
});

test('checkout requests currency and displays returned order rather than repricing it by locale', () => {
  const source = readFileSync(new URL('../src/pages/OperationsPages.jsx', import.meta.url), 'utf8');
  const liveCheckout = source.split('export function CheckoutPage({ navigate }) {')[1]
    ?.split('function LegacyBillingPage({ navigate }) {')[0];
  assert.ok(liveCheckout);
  assert.match(liveCheckout, /currency: selectedQuote\.currency/);
  assert.match(liveCheckout, /returnedOrderId \? orderQuote\(returnedOrder\) : selectedQuote/);
  assert.doesNotMatch(liveCheckout, /Choose an available payment method on Stripe Checkout, such as card or Alipay/);
  assert.match(source, /sales_by_currency/);
});
