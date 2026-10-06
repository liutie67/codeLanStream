/** Own the latest request; aborted or late responses cannot change the UI. */
export function createLatestRequest() {
  let version = 0
  let controller: AbortController | undefined
  let setLoading: ((loading: boolean) => void) | undefined
  return {
    async run<T>(request: (signal: AbortSignal) => Promise<T>, accept: (value: T) => void,
      fail: (error: unknown) => void, loading: (value: boolean) => void) {
      const token = ++version
      controller?.abort()
      // Pagination and folder navigation can own different loading flags.
      // Clear the old owner's flag before handing off to the new request.
      if (setLoading && setLoading !== loading) setLoading(false)
      const current = new AbortController()
      controller = current
      setLoading = loading
      loading(true)
      try {
        const result = await request(current.signal)
        if (token === version) accept(result)
      } catch (error) {
        if (token === version && !current.signal.aborted) fail(error)
      } finally {
        if (token === version) loading(false)
      }
    },
    cancel() {
      version++
      controller?.abort()
      setLoading?.(false)
    },
  }
}
