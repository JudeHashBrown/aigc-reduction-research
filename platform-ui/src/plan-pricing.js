// Prices are minor units from the server catalog, never client-side conversions.
export const preferredPriceCurrency = (isEnglish) => (isEnglish ? 'USD' : 'CNY');

function validQuote(amountMinor, currency) {
  const code = typeof currency === 'string' ? currency.toUpperCase() : '';
  return Number.isSafeInteger(amountMinor) && amountMinor >= 0 && (code === 'CNY' || code === 'USD')
    ? { amount_minor: amountMinor, currency: code }
    : null;
}

export function catalogQuote(plan, currency) {
  if (!plan) return null;
  const code = String(currency || '').toUpperCase();
  if (plan.kind === 'free') return validQuote(0, code);
  const price = plan.prices?.[code];
  if (price && String(price.currency || '').toUpperCase() === code) {
    const quote = validQuote(price.amount_minor, code);
    return quote?.amount_minor > 0 ? quote : null;
  }
  // Older servers only expose a CNY price. Never reinterpret it as USD.
  if (code === 'CNY' && (!plan.currency || String(plan.currency).toUpperCase() === 'CNY')) {
    const quote = validQuote(plan.price_fen, 'CNY');
    return quote?.amount_minor > 0 ? quote : null;
  }
  return null;
}

export function orderQuote(order) {
  if (!order) return null;
  return validQuote(order.amount_minor ?? order.amount_fen, order.currency);
}

export function quotePriceParts(quote, isEnglish) {
  if (!quote) return null;
  return {
    symbol: quote.currency === 'USD' ? '$' : '¥',
    amount: new Intl.NumberFormat(isEnglish ? 'en-US' : 'zh-CN', {
      minimumFractionDigits: 2, maximumFractionDigits: 2,
    }).format(quote.amount_minor / 100),
    code: quote.currency,
  };
}

export function formatMinorPrice(amountMinor, currency, isEnglish, showCode = false) {
  const code = String(currency || '').toUpperCase();
  if (!Number.isSafeInteger(amountMinor) || (code !== 'CNY' && code !== 'USD')) return '—';
  const formatted = new Intl.NumberFormat(isEnglish ? 'en-US' : 'zh-CN', {
    style: 'currency', currency: code, currencyDisplay: 'narrowSymbol',
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(amountMinor / 100);
  return showCode ? `${formatted} ${code}` : formatted;
}

export function formatQuote(quote, isEnglish, showCode = false) {
  return quote ? formatMinorPrice(quote.amount_minor, quote.currency, isEnglish, showCode) : '—';
}
