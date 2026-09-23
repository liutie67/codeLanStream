import { computed, ref } from 'vue'
import type { ImportJobProgress, ImportMediaRequest } from '../api/types'

export const isActiveImport = (job: ImportJobProgress | null) => !!job && ['queued', 'running', 'cancelling'].includes(job.status)

type Tracking = { jobId?: string; requestId?: string; body?: ImportMediaRequest }
interface Dependencies {
  list: (requestId?: string) => Promise<ImportJobProgress[]>
  get: (id: string) => Promise<ImportJobProgress>
  start: (body: ImportMediaRequest) => Promise<ImportJobProgress>
  cancel: (id: string) => Promise<ImportJobProgress>
  storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>
  storageKey: string
  uuid: () => string
}

export function createImportTaskController(api: Dependencies) {
  const visible = ref(false)
  const job = ref<ImportJobProgress | null>(null)
  const activeJob = ref<ImportJobProgress | null>(null)
  const recentJobs = ref<ImportJobProgress[]>([])
  const submitting = ref(false)
  const recovering = ref(false)
  const cancelling = ref(false)
  const connectionError = ref('')
  const actionError = ref('')
  const unavailable = ref(false)
  const revision = ref(0)
  const locked = computed(() => visible.value && (submitting.value || recovering.value || isActiveImport(job.value)))
  let tracking: Tracking | null = null
  let epoch = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  let discoveryTimer: ReturnType<typeof setTimeout> | undefined
  let polling = false
  let discovering = false
  let retryPending = false
  let failures = 0
  let disposed = false
  let initialized = false
  const announced = new Set<string>()

  function persist() {
    try {
      if (tracking) api.storage.setItem(api.storageKey, JSON.stringify(tracking))
      else api.storage.removeItem(api.storageKey)
    } catch {
      actionError.value = '浏览器无法保存任务标识；重新打开后请通过服务器任务入口恢复。'
    }
  }

  function accept(next: ImportJobProgress) {
    if (job.value?.id === next.id) {
      if (!isActiveImport(job.value) && isActiveImport(next)) return
      if (next.updated_at < job.value.updated_at) return
    }
    job.value = next
    tracking = { jobId: next.id, requestId: next.request_id || undefined }
    persist()
    recovering.value = false
    unavailable.value = false
    if (isActiveImport(next)) activeJob.value = next
    else {
      if (activeJob.value?.id === next.id) activeJob.value = null
      if (!announced.has(next.id)) {
        announced.add(next.id)
        revision.value++
      }
    }
  }

  function missing() {
    recovering.value = false
    unavailable.value = true
    job.value = null
    connectionError.value = ''
    actionError.value = '任务记录不可用，服务器已确认记录不存在；无法确认此前的导入结果。'
    // Keep the receipt until the user acknowledges this result.
  }

  function schedule(delay: number) {
    clearTimeout(timer)
    if (!disposed) timer = setTimeout(() => void poll(), delay)
  }

  async function poll() {
    if (polling || submitting.value) {
      retryPending = true
      return
    }
    if (!tracking || disposed || unavailable.value || (job.value && !isActiveImport(job.value))) return
    polling = true
    retryPending = false
    const token = epoch
    const receipt = { ...tracking }
    let delay = 800
    try {
      let next: ImportJobProgress | undefined
      if (receipt.jobId) {
        try {
          next = await api.get(receipt.jobId)
        } catch (error) {
          if ((error as { status?: number }).status !== 404) throw error
          const records = await api.list()
          next = records.find(item => item.id === receipt.jobId)
          // An authoritative list must succeed before declaring a record missing.
        }
      } else if (receipt.requestId) {
        const records = await api.list(receipt.requestId)
        next = records[0]
        if (!next && receipt.body) {
          // A timed-out POST may still be committing. Replay its idempotency key
          // instead of interpreting an early empty list as proof of non-creation.
          try {
            next = await api.start(receipt.body)
          } catch (error) {
            const conflict = error as { status?: number; jobId?: string }
            if (conflict.status === 409 && conflict.jobId) next = await api.get(conflict.jobId)
            else if (conflict.status && conflict.status >= 400 && conflict.status < 500) {
              if (token === epoch) missing()
              return
            } else throw error
          }
        }
      }
      if (token !== epoch || disposed) return
      if (next) accept(next)
      else missing()
      connectionError.value = ''
      failures = 0
    } catch {
      if (token !== epoch || disposed) return
      connectionError.value = '连接中断，服务器任务可能仍在运行。正在自动重试…'
      delay = Math.min(8000, 1000 * 2 ** failures++)
    } finally {
      polling = false
      if (!disposed && tracking && !unavailable.value && (!job.value || isActiveImport(job.value))) {
        schedule(retryPending || token !== epoch ? 0 : delay)
      }
    }
  }

  async function discover() {
    if (discovering || disposed) return
    discovering = true
    try {
      const records = await api.list()
      if (disposed) return
      const previous = activeJob.value
      const finished = previous && records.find(item => item.id === previous.id && !isActiveImport(item))
      if (finished && !announced.has(finished.id)) {
        announced.add(finished.id)
        revision.value++
      }
      activeJob.value = records.find(isActiveImport) || null
      recentJobs.value = records.filter(item => !isActiveImport(item))
    } catch {
      // Discovery failure must not erase a previously known active task.
    } finally {
      discovering = false
      clearTimeout(discoveryTimer)
      if (!disposed) discoveryTimer = setTimeout(() => void discover(), 5000)
    }
  }

  function track(next: ImportJobProgress) {
    epoch++
    clearTimeout(timer)
    job.value = null
    visible.value = true
    connectionError.value = ''
    actionError.value = ''
    accept(next)
    if (isActiveImport(next)) schedule(0)
  }

  function open() {
    if (locked.value) return
    if (activeJob.value) track(activeJob.value)
    else {
      visible.value = true
      void discover().then(() => {
        if (visible.value && !tracking && activeJob.value) track(activeJob.value)
      })
    }
  }

  function close() {
    if (locked.value) return
    epoch++
    clearTimeout(timer)
    visible.value = false
    job.value = null
    tracking = null
    recovering.value = false
    unavailable.value = false
    connectionError.value = ''
    actionError.value = ''
    persist()
    void discover()
  }

  async function start(body: ImportMediaRequest) {
    if (locked.value) return
    epoch++
    const token = epoch
    clearTimeout(timer)
    job.value = null
    visible.value = true
    submitting.value = true
    unavailable.value = false
    actionError.value = ''
    connectionError.value = ''
    const request = { ...body, request_id: api.uuid() }
    tracking = { requestId: request.request_id, body: request }
    persist()
    try {
      const next = await api.start(request)
      if (token === epoch && !disposed) accept(next)
    } catch (error) {
      if (token !== epoch || disposed) return
      const failure = error as { status?: number; jobId?: string; message?: string }
      if (failure.status === 409 && failure.jobId) {
        tracking = { jobId: failure.jobId }
        recovering.value = true
        persist()
      } else if (failure.status && failure.status >= 400 && failure.status < 500) {
        tracking = null
        persist()
        actionError.value = failure.message || '导入请求被拒绝'
      } else {
        recovering.value = true
        connectionError.value = '创建结果尚未确认，正在恢复任务；请勿重复发起导入。'
      }
    } finally {
      if (token === epoch && !disposed) {
        submitting.value = false
        if (tracking) schedule(0)
      }
    }
  }

  async function cancel() {
    if (!job.value || !isActiveImport(job.value) || cancelling.value || job.value.status === 'cancelling') return
    cancelling.value = true
    actionError.value = ''
    const id = job.value.id
    const token = epoch
    try {
      const next = await api.cancel(id)
      if (token === epoch && !disposed) accept(next)
    } catch {
      if (token === epoch && !disposed) actionError.value = '终止请求未确认，请重试；任务仍可能在运行。'
    } finally {
      cancelling.value = false
      if (token === epoch && !disposed) schedule(0)
    }
  }

  function retry() { clearTimeout(timer); void poll() }

  function initialize() {
    if (initialized) return
    initialized = true
    try {
      const stored = JSON.parse(api.storage.getItem(api.storageKey) || 'null') as Tracking | null
      if (stored && (typeof stored.jobId === 'string' || typeof stored.requestId === 'string')) {
        tracking = stored
        visible.value = true
        recovering.value = true
        schedule(0)
      }
    } catch { /* Ignore invalid local receipts; server discovery is still available. */ }
    void discover()
  }

  function dispose() {
    disposed = true
    epoch++
    clearTimeout(timer)
    clearTimeout(discoveryTimer)
  }

  return { visible, job, activeJob, recentJobs, submitting, recovering, cancelling, locked, connectionError,
    actionError, unavailable, revision, initialize, dispose, open, close, track, start, cancel, retry, discover }
}
