import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchBrowse, mediaRequest } from './client'

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })
describe('media requests', () => {
  it('requests only the selected folder page', async () => {
    const fetch = vi.fn(async (_url: string, _init?: RequestInit) => ({ ok: true, json: async () => ({ items: [], has_next: false }) }))
    vi.stubGlobal('fetch', fetch)
    await fetchBrowse('/media', 'photos', 'image', undefined, 3, '/media/photos/last.jpg')
    const query = new URL(fetch.mock.calls[0]![0] as string, 'http://localhost').searchParams
    expect(query.get('page')).toBe('3')
    expect(query.get('page_size')).toBe('60')
    expect(query.get('subdir')).toBe('photos')
    expect(query.get('after_path')).toBe('/media/photos/last.jpg')
  })
  it('turns directory HTTP failures into actionable errors', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404, json: async () => ({ detail: '目录已不存在' }) })))
    await expect(fetchBrowse('/media', 'gone')).rejects.toThrow('目录已不存在')
  })
  it('times out a stalled disk request and aborts fetch', async () => {
    vi.useFakeTimers()
    let signal: AbortSignal | undefined
    vi.stubGlobal('fetch', vi.fn((_url, init: RequestInit) => new Promise((_resolve, reject) => {
      signal = init.signal as AbortSignal
      signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    })))
    const request = expect(mediaRequest('/browse')).rejects.toThrow('读取超时')
    await vi.advanceTimersByTimeAsync(10_000)
    await request
    expect(signal?.aborted).toBe(true)
  })
  it('preserves external cancellation without reporting it as a timeout', async () => {
    const controller = new AbortController()
    vi.stubGlobal('fetch', vi.fn((_url, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    })))
    const request = expect(fetchBrowse('/media', undefined, undefined, controller.signal)).rejects.toMatchObject({ name: 'AbortError' })
    controller.abort()
    await request
  })
})
