/**
 * sessionStorage 기반 stale-while-revalidate 캐시.
 * 브라우저 리프레시 시 이전 데이터를 즉시 표시하고, 백그라운드에서 갱신.
 */

const CACHE_PREFIX = 'ats:';
const DEFAULT_TTL_MS = 5 * 60 * 1000; // 5분

export function getCached<T>(key: string): T | null {
  try {
    const raw = sessionStorage.getItem(CACHE_PREFIX + key);
    if (!raw) return null;
    const { data, ts } = JSON.parse(raw);
    if (Date.now() - ts > DEFAULT_TTL_MS) {
      sessionStorage.removeItem(CACHE_PREFIX + key);
      return null;
    }
    return data as T;
  } catch {
    return null;
  }
}

export function setCache(key: string, data: unknown): void {
  try {
    sessionStorage.setItem(
      CACHE_PREFIX + key,
      JSON.stringify({ data, ts: Date.now() })
    );
  } catch {
    // sessionStorage full or unavailable — ignore
  }
}
