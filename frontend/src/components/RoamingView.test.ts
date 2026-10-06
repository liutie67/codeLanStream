import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, nextTick, ref } from 'vue'
import type { MediaItem } from '../api/types'

const api = vi.hoisted(() => ({ random: vi.fn(), recheck: vi.fn(), favorite: vi.fn() }))
vi.mock('../api/client', () => ({
  fetchRandom: api.random, fetchFeed: vi.fn(), recheckMedia: api.recheck,
  toggleFavorite: api.favorite, toggleDelete: vi.fn(), toggleDamaged: vi.fn(),
  getStreamUrl: (id: string) => `/stream/${id}`,
  getThumbnailUrl: (id: string) => `/thumbnail/${id}`,
  getPreviewUrl: (id: string) => `/preview/${id}`,
}))
vi.mock('../composables/useThumbnailMode', () => ({ useThumbnailMode: () => ({ thumbMode: ref('first-frame') }) }))
vi.mock('../composables/useTheme', () => ({ useTheme: () => ({ isDark: ref(true) }) }))
vi.mock('../composables/useSwipe', () => ({ useSwipe: () => ({ attach: vi.fn(), detach: vi.fn() }) }))
vi.mock('../utils/mediaResource', () => ({
  createPreloadImage: vi.fn(), createDetachedVideoPreloader: vi.fn(),
  releaseImageElement: vi.fn(), releaseMediaElement: vi.fn(), updateDetachedVideoPreload: vi.fn(),
}))
import RoamingView from './RoamingView.vue'

// Render the actual component and dispatch its events without a browser or
// extra DOM dependency. Host nodes retain props, keys and parent relationships.
class HostNode {
  children: HostNode[] = []
  parent: HostNode | null = null
  props: Record<string, any> = {}
  style: Record<string, string> = {}
  type: string
  text: string
  constructor(type: string, text = '') { this.type = type; this.text = text }
  getAttribute(name: string) { return this.props[name] ?? null }
}
function insert(node: HostNode, parent: HostNode, anchor: HostNode | null = null) {
  remove(node)
  const index = anchor ? parent.children.indexOf(anchor) : -1
  parent.children.splice(index < 0 ? parent.children.length : index, 0, node)
  node.parent = parent
}
function remove(node: HostNode) {
  if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1)
  node.parent = null
}
const renderer = createRenderer<HostNode, HostNode>({
  insert, remove, createElement: tag => new HostNode(tag),
  createText: text => new HostNode('text', text), createComment: text => new HostNode('comment', text),
  setText: (node, text) => { node.text = text },
  setElementText: (node, text) => { node.text = text; node.children = [] },
  patchProp: (node, key, _old, value) => { node.props[key] = value },
  parentNode: node => node.parent,
  nextSibling: node => node.parent?.children[node.parent.children.indexOf(node) + 1] || null,
  insertStaticContent: (content, parent, anchor) => {
    const node = new HostNode('static', content)
    insert(node, parent, anchor)
    return [node, node]
  },
})
function all(node: HostNode): HostNode[] { return [node, ...node.children.flatMap(all)] }
function photo(id: string): MediaItem {
  return { id, file_path: `/photos/${id}.jpg`, media_type: 'image', folder: '/photos',
    root_dir: '/photos', size_bytes: 5, duration: null, width: 100, height: 100,
    thumbnail_path: null, preview_path: null, is_favorited: false, is_deleted: false,
    is_damaged: false, availability: 'available', availability_checked_at: null,
    created_at: '' }
}
const rows = [photo('a'), photo('b'), photo('c')]
let root: HostNode
let app: ReturnType<typeof renderer.createApp>
let listeners: Map<string, (event: any) => void>
async function flush() { for (let i = 0; i < 5; i++) await nextTick() }
function image(id: string) { return all(root).find(node => node.type === 'img' && node.props.src === `/stream/${id}`)! }
function retry() { return all(root).find(node => node.type === 'button' && node.text === '重试')! }
async function key(code: string, eventType = 'keydown') {
  listeners.get(eventType)!({ code, key: code, preventDefault: vi.fn(), target: {}, repeat: false })
  await flush()
  await vi.advanceTimersByTimeAsync(210)
  await flush()
}
beforeEach(async () => {
  vi.useFakeTimers()
  api.random.mockReset().mockResolvedValue({ items: rows, total: rows.length })
  api.recheck.mockReset().mockImplementation(async ([id]: string[]) => [photo(id)])
  api.favorite.mockReset().mockImplementation(async (id: string) => ({ ...photo(id), is_favorited: true }))
  listeners = new Map()
  vi.stubGlobal('window', { innerHeight: 800, innerWidth: 1200, setTimeout: vi.fn(),
    addEventListener: (type: string, listener: (event: any) => void) => listeners.set(type, listener),
    removeEventListener: (type: string) => listeners.delete(type) })
  vi.stubGlobal('HTMLElement', HostNode)
  vi.stubGlobal('HTMLImageElement', HostNode)
  vi.stubGlobal('requestAnimationFrame', (callback: () => void) => callback())
  root = new HostNode('root')
  app = renderer.createApp(RoamingView)
  app.mount(root)
  await flush()
})
afterEach(() => { app.unmount(); vi.useRealTimers(); vi.unstubAllGlobals() })

describe('roaming image failures', () => {
  it('retries only the current image and retains the previous and next items', async () => {
    await key('KeyS')
    const failed = image('b')
    await failed.props.onError({ target: failed })
    await flush()
    expect(failed.style.visibility).toBeUndefined()
    expect(all(root).some(node => node.type === 'img' && node.props.src === '/stream/b')).toBe(false)
    retry().props.onClick()
    await flush()
    expect(api.random).toHaveBeenCalledTimes(1)
    expect(image('a')).toBeDefined()
    expect(image('c')).toBeDefined()
    const refreshed = all(root).find(node => node.props.src === '/stream/b?retry=1')!
    expect(refreshed).toBeDefined()
    expect(refreshed).not.toBe(failed)
    await key('KeyW')
    expect(image('a')).toBeDefined()
    expect(all(root).find(node => node.type === 'p' && node.text === 'a.jpg')).toBeDefined()
  })
  it('retains undo history when retrying after a classification action', async () => {
    await key('KeyF')
    await key('KeyF', 'keyup')
    const failed = image('b')
    await failed.props.onError({ target: failed })
    await flush()
    retry().props.onClick()
    await flush()
    await key('KeyW')
    expect(api.favorite.mock.calls.map(call => call[0])).toEqual(['a', 'a'])
    expect(api.random).toHaveBeenCalledTimes(1)
  })
  it('waits for fresh file metadata before mounting the retried image', async () => {
    const failed = image('a')
    await failed.props.onError({ target: failed })
    await flush()
    let finish!: (items: MediaItem[]) => void
    api.recheck.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const retrying = retry().props.onClick()
    await flush()
    expect(all(root).some(node => node.type === 'img' && String(node.props.src).includes('/stream/a'))).toBe(false)
    expect(all(root).find(node => node.text === '正在重试…')).toBeDefined()
    finish([photo('a')])
    await retrying
    await flush()
    expect(all(root).find(node => node.props.src === '/stream/a?retry=1')).toBeDefined()
    expect(api.random).toHaveBeenCalledTimes(1)
  })
  it('ignores an old failed recheck after the user has retried the image', async () => {
    let finish!: (items: MediaItem[]) => void
    api.recheck.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const failed = image('a')
    const checking = failed.props.onError({ target: failed })
    await flush()
    retry().props.onClick()
    await flush()
    finish([{ ...photo('a'), availability: 'missing' }])
    await checking
    await flush()
    expect(all(root).find(node => node.props.src === '/stream/a?retry=1')).toBeDefined()
    expect(image('b')).toBeDefined()
    expect(api.random).toHaveBeenCalledTimes(1)
  })
})
