/**
 * Currency helpers for FuturesTrading page.
 *
 * 한국 지수 (KS200/KQ11/KQ150) 는 ₩(KRW), 나머지는 $(USD) 로 포맷.
 *
 * Phase 3.C 분할: pages/FuturesTrading.tsx → components/futures-trading/currency.ts
 */

export const KRW_TICKERS = new Set(['^KS200', '^KQ11', '^KQ150']);

export function getTickerCurrency(ticker: string): { symbol: string; locale: string; code: string } {
  if (KRW_TICKERS.has(ticker)) {
    return { symbol: '₩', locale: 'ko-KR', code: 'KRW' };
  }
  return { symbol: '$', locale: 'en-US', code: 'USD' };
}

export function formatPrice(value: number, ticker: string, decimals = 2): string {
  const { symbol, locale } = getTickerCurrency(ticker);
  return `${symbol}${value.toLocaleString(locale, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
}

export function formatPnL(value: number, ticker: string): string {
  const { symbol, locale } = getTickerCurrency(ticker);
  if (value < 0) return `-${symbol}${Math.abs(value).toLocaleString(locale)}`;
  return `${symbol}${value.toLocaleString(locale)}`;
}
