import { describe, expect, it, vi } from 'vitest'
import { createLatestRequest } from './latestRequest'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

describe('latest directory request', () => {
  it('ignores late responses after navigating to another folder', async () => {
    const controller = createLatestRequest()
    const first = deferred<string>()
    const second = deferred<string>()
    const accept = vi.fn()
    const failure = vi.fn()
    const loading = vi.fn()
    let signal: AbortSignal | undefined
    const old = controller.run(current => { signal = current; return first.promise }, accept, failure, loading)
    const latest = controller.run(() => second.promise, accept, failure, loading)
    expect(signal?.aborted).toBe(true)
    first.resolve('old-folder')
    await old
    expect(accept).not.toHaveBeenCalled()
    expect(loading).not.toHaveBeenCalledWith(false)
    second.resolve('new-folder')
    await latest
    expect(accept).toHaveBeenCalledExactlyOnceWith('new-folder')
    expect(loading).toHaveBeenLastCalledWith(false)
  })
  it('ends loading on errors and allows retry', async () => {
    const controller = createLatestRequest()
    const loading = vi.fn()
    const failure = vi.fn()
    const accept = vi.fn()
    await controller.run(() => Promise.reject(new Error('目录已不存在')), accept, failure, loading)
    expect(failure).toHaveBeenCalledOnce()
    expect(loading).toHaveBeenLastCalledWith(false)
    await controller.run(() => Promise.resolve('restored'), accept, failure, loading)
    expect(accept).toHaveBeenCalledWith('restored')
  })
  it('clears a pending load-more flag when switching folders', async () => {
    const controller = createLatestRequest()
    const oldPage = deferred<string>()
    const nextFolder = deferred<string>()
    let loadingMore = false
    let loadingFolder = false
    const old = controller.run(() => oldPage.promise, vi.fn(), vi.fn(), value => { loadingMore = value })
    const latest = controller.run(() => nextFolder.promise, vi.fn(), vi.fn(), value => { loadingFolder = value })
    expect(loadingMore).toBe(false)
    expect(loadingFolder).toBe(true)
    oldPage.resolve('old-page')
    await old
    expect(loadingFolder).toBe(true)
    nextFolder.resolve('new-folder')
    await latest
    expect(loadingFolder).toBe(false)
    await controller.run(() => Promise.resolve('next-page'), vi.fn(), vi.fn(), value => { loadingMore = value })
    expect(loadingMore).toBe(false)
  })
  it('closing or returning home cancels requests without publishing errors', async () => {
    const controller = createLatestRequest()
    const pending = deferred<string>()
    const accept = vi.fn()
    const failure = vi.fn()
    const loading = vi.fn()
    const request = controller.run(() => pending.promise, accept, failure, loading)
    controller.cancel()
    expect(loading).toHaveBeenLastCalledWith(false)
    pending.reject(new Error('late network failure'))
    await request
    expect(accept).not.toHaveBeenCalled()
    expect(failure).not.toHaveBeenCalled()
  })
})
