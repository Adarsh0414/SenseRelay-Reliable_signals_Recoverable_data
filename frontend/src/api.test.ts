import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiFetch, getDemoStatus, resetDemoDataset, seedDemoDataset } from './api';

afterEach(() => vi.unstubAllGlobals());

describe('apiFetch', () => {
  it('includes same-origin credentials and parses JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(apiFetch<{ ok: boolean }>('/api/health')).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith('/api/health', expect.objectContaining({ credentials: 'same-origin', cache: 'no-store' }));
  });

  it('raises a useful ApiError on a failed API response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Sign-in required' }), {
      status: 401, headers: { 'Content-Type': 'application/json' },
    })));
    await expect(apiFetch('/api/dashboard/summary')).rejects.toMatchObject({ message: 'Sign-in required', status: 401 });
  });
});


describe('persistent synthetic demo fixture API', () => {
  it('reads fixture status from the backend, not frontend constants', async () => {
    const status = { enabled: true, seeded: false, session_id: 'maya-demo-seed7-v1', seed: 7 };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(status), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(getDemoStatus()).resolves.toMatchObject(status);
    expect(fetchMock).toHaveBeenCalledWith('/api/dashboard/demo/status', expect.objectContaining({ cache: 'no-store' }));
  });

  it('uses explicit backend actions to seed and reset the single demo session', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true, session_id: 'maya-demo-seed7-v1' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true, session_id: 'maya-demo-seed7-v1', notice: 'removed' }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(seedDemoDataset()).resolves.toMatchObject({ ok: true });
    await expect(resetDemoDataset()).resolves.toMatchObject({ ok: true });
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/dashboard/demo/seed', expect.objectContaining({ method: 'POST', credentials: 'same-origin' }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/dashboard/demo/reset', expect.objectContaining({ method: 'POST', credentials: 'same-origin' }));
  });
});
