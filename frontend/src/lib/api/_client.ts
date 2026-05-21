/**
 * API Client Configuration
 *
 * 모든 도메인 API 모듈이 공유하는 base URL / 환경 플래그 / fetch 헬퍼.
 * Phase 3.A 분할 시 신설, 3.A-2에서 fetchOrMock 헬퍼 추가.
 */

export const API_BASE_URL =
    import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

export const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';

/**
 * 모의 모드(VITE_USE_MOCK=true)면 mockFn 사용, 아니면 실제 API 호출.
 * 8초 timeout. operations/market/sim 도메인에서 공유.
 */
export async function fetchOrMock<T>(url: string, mockFn: () => T): Promise<T> {
    if (USE_MOCK) return mockFn();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
        const response = await fetch(`${API_BASE_URL}${url}`, { signal: controller.signal });
        if (!response.ok) throw new Error(`API error: ${response.status}`);
        return response.json();
    } finally {
        clearTimeout(timeout);
    }
}
