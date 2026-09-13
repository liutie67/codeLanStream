import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createImportTaskController } from './importTaskController'
import type { ImportJobProgress, ImportMediaRequest } from '../api/types'

const request: ImportMediaRequest = { path: '/media', preview: false, recursive: true, skip_hidden: true, backfill_existing: true }
function job(status: ImportJobProgress['status'] = 'running', id = 'job-1', time = '2026-09-06T10:00:00.000001'): ImportJobProgress {
  return { id, request_id: 'request-1', options: request, status, stage: status === 'running' ? 'scanning' : status, message: status, percent: 30,
    current: 1, total: 5, current_file: null, error: null, created_at: time, updated_at: time,
    stats: { root_dir: '/media', scanned_files: 1, added_count: 1, existing_count: 0, skipped_count: 0,
      thumbnail_count: 0, preview_count: 0, preview_requested: false } }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
const controllers: ReturnType<typeof createImportTaskController>[] = []
function setup(receipt?: object) {
  const values = new Map<string, string>()
  if (receipt) values.set('task', JSON.stringify(receipt))
  const api = {
    list: vi.fn(async (_requestId?: string): Promise<ImportJobProgress[]> => []),
    get: vi.fn(async (_id: string) => job()),
    start: vi.fn(async (_body: ImportMediaRequest) => job()),
    cancel: vi.fn(async (_id: string) => job('cancelling', 'job-1', '2026-09-06T10:00:01')),
    storage: { getItem: (key: string) => values.get(key) || null, setItem: (key: string, value: string) => { values.set(key, value) }, removeItem: (key: string) => { values.delete(key) } },
    storageKey: 'task', uuid: () => 'request-1',
  }
  const task = createImportTaskController(api)
  controllers.push(task)
  return { task, api, values }
}
beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  controllers.splice(0).forEach(task => task.dispose())
  vi.useRealTimers()
})

describe('global import task lifecycle', () => {
  it('locks immediately before the create response and ignores close', async () => {
    const { task, api, values } = setup()
    const pending = deferred<ImportJobProgress>()
    api.start.mockReturnValue(pending.promise)
    const start = task.start(request)
    expect(task.locked.value).toBe(true)
    expect(JSON.parse(values.get('task')!).requestId).toBe('request-1')
    task.close()
    expect(task.visible.value).toBe(true)
    pending.resolve(job())
    await start
    expect(task.locked.value).toBe(true)
  })

  it('keeps progress and lock on disconnect, then unlocks only for terminal state', async () => {
    const { task, api } = setup()
    api.get.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(job('completed', 'job-1', '2026-09-06T10:00:02'))
    task.track(job())
    await vi.advanceTimersByTimeAsync(0)
    expect(task.connectionError.value).toContain('连接中断')
    expect(task.job.value?.percent).toBe(30)
    expect(task.locked.value).toBe(true)
    await vi.advanceTimersByTimeAsync(1000)
    expect(task.locked.value).toBe(false)
    expect(task.visible.value).toBe(true)
    expect(task.revision.value).toBe(1)
    task.close()
    expect(task.visible.value).toBe(false)
  })

  it('serializes polling and queues immediate retry without overlapping requests', async () => {
    const { task, api } = setup()
    const pending = deferred<ImportJobProgress>()
    api.get.mockReturnValueOnce(pending.promise)
    task.track(job())
    await vi.advanceTimersByTimeAsync(0)
    task.retry()
    task.retry()
    await vi.advanceTimersByTimeAsync(5000)
    expect(api.get).toHaveBeenCalledTimes(1)
    pending.resolve(job())
    await vi.advanceTimersByTimeAsync(1)
    expect(api.get).toHaveBeenCalledTimes(2)
  })

  it('rejects an old running response after cancellation is acknowledged', async () => {
    const { task, api } = setup()
    const pending = deferred<ImportJobProgress>()
    api.get.mockReturnValueOnce(pending.promise)
    task.track(job())
    await vi.advanceTimersByTimeAsync(0)
    await task.cancel()
    pending.resolve(job())
    await vi.advanceTimersByTimeAsync(1)
    expect(task.job.value?.status).toBe('cancelling')
    expect(task.locked.value).toBe(true)
  })

  it('cannot regress terminal state when a prior request finishes late', async () => {
    const { task, api } = setup()
    const pending = deferred<ImportJobProgress>()
    api.get.mockReturnValueOnce(pending.promise)
    api.cancel.mockResolvedValue(job('completed', 'job-1', '2026-09-06T10:00:02'))
    task.track(job())
    await vi.advanceTimersByTimeAsync(0)
    await task.cancel()
    pending.resolve(job())
    await vi.advanceTimersByTimeAsync(1)
    expect(task.job.value?.status).toBe('completed')
    expect(task.locked.value).toBe(false)
  })

  it('restores saved task before requests return and preserves unacknowledged result', async () => {
    const { task, api, values } = setup({ jobId: 'job-1' })
    api.get.mockResolvedValue(job('interrupted'))
    task.initialize()
    expect(task.visible.value).toBe(true)
    expect(task.locked.value).toBe(true)
    await vi.advanceTimersByTimeAsync(0)
    expect(task.job.value?.status).toBe('interrupted')
    expect(task.locked.value).toBe(false)
    expect(values.has('task')).toBe(true)
    task.close()
    expect(values.has('task')).toBe(false)
  })

  it('discovers tasks on another device without automatically opening the modal', async () => {
    const { task, api } = setup()
    api.list.mockResolvedValue([job()])
    task.initialize()
    await vi.advanceTimersByTimeAsync(0)
    expect(task.activeJob.value?.id).toBe('job-1')
    expect(task.visible.value).toBe(false)
    task.open()
    expect(task.locked.value).toBe(true)
  })

  it('recovers a lost creation response using its request ID', async () => {
    const { task, api } = setup()
    api.start.mockRejectedValueOnce(new Error('timeout'))
    api.list.mockResolvedValue([job()])
    await task.start(request)
    expect(task.locked.value).toBe(true)
    await vi.advanceTimersByTimeAsync(0)
    expect(api.list).toHaveBeenCalledWith('request-1')
    expect(api.start).toHaveBeenCalledTimes(1)
    expect(task.job.value?.id).toBe('job-1')
  })

  it('replays the same key if an empty lookup races a delayed creation commit', async () => {
    const { task, api } = setup()
    api.start.mockRejectedValueOnce(new Error('timeout')).mockResolvedValueOnce(job())
    await task.start(request)
    await vi.advanceTimersByTimeAsync(0)
    expect(api.start).toHaveBeenCalledTimes(2)
    expect(api.start.mock.calls[0]![0].request_id).toBe(api.start.mock.calls[1]![0].request_id)
    expect(task.locked.value).toBe(true)
  })

  it('attaches to an existing server task on creation conflict', async () => {
    const { task, api } = setup()
    api.start.mockRejectedValue({ status: 409, jobId: 'job-1' })
    await task.start(request)
    await vi.advanceTimersByTimeAsync(0)
    expect(api.get).toHaveBeenCalledWith('job-1')
    expect(task.locked.value).toBe(true)
  })

  it('does not unlock on 404 until the authoritative list succeeds', async () => {
    const { task, api } = setup()
    api.get.mockRejectedValue({ status: 404 })
    api.list.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce([])
    task.track(job())
    await vi.advanceTimersByTimeAsync(0)
    expect(task.locked.value).toBe(true)
    await vi.advanceTimersByTimeAsync(1000)
    expect(task.unavailable.value).toBe(true)
    expect(task.locked.value).toBe(false)
    expect(task.actionError.value).toContain('记录不存在')
  })

  it('does not unlock or hide a task when cancellation response is lost', async () => {
    const { task, api } = setup()
    api.cancel.mockRejectedValue(new Error('timeout'))
    task.track(job())
    await task.cancel()
    expect(task.locked.value).toBe(true)
    expect(task.actionError.value).toContain('未确认')
    await task.cancel()
    expect(api.cancel).toHaveBeenCalledTimes(2)
  })

  it('ignores responses for a replaced task', async () => {
    const { task, api } = setup()
    const pending = deferred<ImportJobProgress>()
    api.get.mockReturnValueOnce(pending.promise)
    task.track(job())
    await vi.advanceTimersByTimeAsync(0)
    task.track(job('completed', 'job-2'))
    pending.resolve(job())
    await vi.advanceTimersByTimeAsync(1)
    expect(task.job.value?.id).toBe('job-2')
    expect(task.locked.value).toBe(false)
  })

  it('retains active discovery state if the network becomes unavailable', async () => {
    const { task, api } = setup()
    api.list.mockResolvedValueOnce([job()]).mockRejectedValueOnce(new Error('offline'))
    await task.discover()
    await task.discover()
    expect(task.activeJob.value?.id).toBe('job-1')
  })
})
