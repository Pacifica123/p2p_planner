import { apiRequest, clearAccessToken, setAccessToken } from '@/shared/api/client';

describe('apiRequest', () => {
  it('unwraps the data envelope and sends authorization header', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const headers = new Headers(init?.headers);

      expect(headers.get('Authorization')).toBe('Bearer access-token');
      expect(headers.get('Content-Type')).toBe('application/json');

      return new Response(JSON.stringify({ data: { ok: true } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    vi.stubGlobal('fetch', fetchMock);
    setAccessToken('access-token');

    await expect(
      apiRequest<{ ok: boolean }>('/test', {
        method: 'POST',
        body: JSON.stringify({ hello: 'world' }),
      }),
    ).resolves.toEqual({ ok: true });

    clearAccessToken();
  });

  it('throws a network ApiError when fetch fails before a response exists', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('socket hang up');
      }),
    );

    await expect(apiRequest('/test')).rejects.toMatchObject({
      name: 'ApiError',
      status: 0,
      code: 'NETWORK_ERROR',
    });

    await expect(apiRequest('/test')).rejects.toThrow('Не удалось связаться с backend');
  });
});
