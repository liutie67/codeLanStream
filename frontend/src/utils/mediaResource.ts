export function releaseMediaElement(element: HTMLMediaElement | null | undefined) {
  if (!element) return

  element.pause()
  element.removeAttribute('src')
  element.querySelectorAll('source').forEach(source => source.removeAttribute('src'))

  try {
    element.load()
  } catch {
    // Some browsers can throw if a detached element is already torn down.
  }
}

export function releaseImageElement(element: HTMLImageElement | null | undefined) {
  if (!element) return

  element.onload = null
  element.onerror = null
  element.removeAttribute('src')
}

export function createPreloadImage(src?: string) {
  const image = new Image()
  image.decoding = 'async'
  if (src) image.src = src
  return image
}

export function createDetachedVideoPreloader(src: string, preload: 'metadata' | 'auto') {
  const video = document.createElement('video')
  video.preload = preload
  video.muted = true
  video.playsInline = true
  video.setAttribute('playsinline', 'true')
  video.src = src
  video.load()
  return video
}

export function updateDetachedVideoPreload(video: HTMLVideoElement, preload: 'metadata' | 'auto') {
  if (video.preload === preload) return

  video.preload = preload
  video.load()
}
