<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { DirectoryListResponse, ImportMediaResponse, MediaType } from '../api/types'
import { fetchDirectories, importMediaFolder } from '../api/client'
import { useTheme } from '../composables/useTheme'

const emit = defineEmits<{ close: []; imported: [result: ImportMediaResponse] }>()
const { isDark } = useTheme()

const path = ref('')
const directoryList = ref<DirectoryListResponse | null>(null)
const loadingDirs = ref(false)
const importing = ref(false)
const error = ref('')
const result = ref<ImportMediaResponse | null>(null)

const preview = ref(false)
const mediaType = ref<MediaType | 'all'>('all')
const recursive = ref(true)
const skipHidden = ref(true)
const backfillExisting = ref(true)
const workers = ref(4)

const typeOptions: { value: MediaType | 'all'; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'video', label: '视频' },
  { value: 'image', label: '图片' },
]

const canImport = computed(() => path.value.trim().length > 0 && !importing.value)

async function loadDirectory(target?: string) {
  loadingDirs.value = true
  error.value = ''
  try {
    const res = await fetchDirectories(target)
    directoryList.value = res
    path.value = res.path
  } catch (e: any) {
    error.value = e.message || '目录读取失败'
  } finally {
    loadingDirs.value = false
  }
}

async function submit() {
  if (!canImport.value) return
  importing.value = true
  error.value = ''
  result.value = null
  try {
    const res = await importMediaFolder({
      path: path.value.trim(),
      preview: preview.value,
      media_type: mediaType.value === 'all' ? null : mediaType.value,
      recursive: recursive.value,
      skip_hidden: skipHidden.value,
      backfill_existing: backfillExisting.value,
      workers: preview.value ? workers.value : null,
    })
    result.value = res
    emit('imported', res)
  } catch (e: any) {
    error.value = e.message || '导入失败'
  } finally {
    importing.value = false
  }
}

onMounted(() => loadDirectory())
</script>

<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-[70] bg-black/70 flex items-center justify-center p-3" @click.self="emit('close')">
      <section
        :class="[
          'w-full max-w-3xl max-h-[92vh] overflow-hidden rounded-xl border shadow-2xl flex flex-col',
          isDark ? 'bg-gray-950 border-gray-800 text-white' : 'bg-white border-gray-200 text-gray-900',
        ]"
      >
        <header :class="['px-4 py-3 border-b flex items-center justify-between gap-3', isDark ? 'border-gray-800' : 'border-gray-200']">
          <div>
            <h2 class="text-sm font-semibold">导入媒体</h2>
            <p class="text-xs text-gray-500 mt-0.5">选择服务器本机目录</p>
          </div>
          <button
            @click="emit('close')"
            class="w-8 h-8 flex items-center justify-center rounded-full text-gray-400 hover:text-white transition-colors"
            title="关闭"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </header>

        <div class="overflow-y-auto p-4 space-y-4">
          <div class="flex flex-col md:flex-row gap-2">
            <input
              v-model="path"
              :class="[
                'flex-1 min-w-0 px-3 py-2 rounded-lg border text-sm font-mono',
                isDark ? 'bg-gray-900 border-gray-700 text-white' : 'bg-white border-gray-300 text-gray-900',
              ]"
              placeholder="/path/to/media"
            />
            <button
              @click="loadDirectory(path)"
              :disabled="loadingDirs || !path.trim()"
              :class="[
                'h-10 px-3 rounded-lg border text-sm font-medium transition-colors disabled:opacity-50',
                isDark ? 'border-gray-700 bg-gray-800 hover:bg-gray-700' : 'border-gray-300 bg-gray-100 hover:bg-gray-200',
              ]"
            >
              打开
            </button>
          </div>

          <div :class="['rounded-lg border overflow-hidden', isDark ? 'border-gray-800' : 'border-gray-200']">
            <div :class="['px-3 py-2 border-b flex items-center justify-between gap-2', isDark ? 'border-gray-800 bg-gray-900' : 'border-gray-200 bg-gray-50']">
              <span class="text-xs font-mono truncate">{{ directoryList?.path || '...' }}</span>
              <button
                v-if="directoryList?.parent"
                @click="loadDirectory(directoryList.parent)"
                class="shrink-0 text-xs text-blue-400 hover:text-blue-300"
              >
                上级
              </button>
            </div>
            <div class="max-h-60 overflow-y-auto">
              <button
                v-for="dir in directoryList?.directories || []"
                :key="dir.path"
                @click="loadDirectory(dir.path)"
                :class="[
                  'w-full px-3 py-2 flex items-center gap-2 text-left text-sm border-b last:border-b-0 transition-colors',
                  isDark ? 'border-gray-800 hover:bg-gray-900' : 'border-gray-100 hover:bg-gray-50',
                ]"
              >
                <svg class="w-4 h-4 shrink-0 text-yellow-400" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M10 4H4a2 2 0 00-2 2v12a2 2 0 002 2h16a2 2 0 002-2V8a2 2 0 00-2-2h-8l-2-2z" />
                </svg>
                <span class="truncate">{{ dir.name }}</span>
              </button>
              <div v-if="loadingDirs" class="px-3 py-6 text-center text-sm text-gray-500">读取中...</div>
              <div v-else-if="directoryList && directoryList.directories.length === 0" class="px-3 py-6 text-center text-sm text-gray-500">无子目录</div>
            </div>
          </div>

          <div class="grid gap-3 md:grid-cols-2">
            <div>
              <label class="block text-xs text-gray-500 mb-1.5">视频处理</label>
              <div :class="['inline-flex rounded-full p-0.5', isDark ? 'bg-gray-800' : 'bg-gray-200']">
                <button
                  @click="preview = false"
                  :class="[
                    'px-3 py-1 rounded-full text-xs font-medium transition-colors',
                    !preview ? 'bg-blue-600 text-white' : isDark ? 'text-gray-400 hover:text-gray-200' : 'text-gray-500 hover:text-gray-700',
                  ]"
                >
                  首帧
                </button>
                <button
                  @click="preview = true"
                  :class="[
                    'px-3 py-1 rounded-full text-xs font-medium transition-colors',
                    preview ? 'bg-emerald-600 text-white' : isDark ? 'text-gray-400 hover:text-gray-200' : 'text-gray-500 hover:text-gray-700',
                  ]"
                >
                  预览
                </button>
              </div>
            </div>

            <div>
              <label class="block text-xs text-gray-500 mb-1.5">导入类型</label>
              <div :class="['inline-flex rounded-full p-0.5', isDark ? 'bg-gray-800' : 'bg-gray-200']">
                <button
                  v-for="option in typeOptions"
                  :key="option.value"
                  @click="mediaType = option.value"
                  :class="[
                    'px-3 py-1 rounded-full text-xs font-medium transition-colors',
                    mediaType === option.value ? 'bg-blue-600 text-white' : isDark ? 'text-gray-400 hover:text-gray-200' : 'text-gray-500 hover:text-gray-700',
                  ]"
                >
                  {{ option.label }}
                </button>
              </div>
            </div>

            <label class="flex items-center gap-2 text-sm">
              <input v-model="recursive" type="checkbox" class="w-4 h-4 accent-blue-500" />
              <span>递归子目录</span>
            </label>
            <label class="flex items-center gap-2 text-sm">
              <input v-model="skipHidden" type="checkbox" class="w-4 h-4 accent-blue-500" />
              <span>跳过隐藏文件</span>
            </label>
            <label class="flex items-center gap-2 text-sm">
              <input v-model="backfillExisting" type="checkbox" class="w-4 h-4 accent-blue-500" />
              <span>补齐已有媒体</span>
            </label>
            <label class="flex items-center gap-2 text-sm">
              <span class="text-gray-500">预览并发</span>
              <input
                v-model.number="workers"
                type="number"
                min="1"
                max="16"
                :disabled="!preview"
                :class="[
                  'w-20 px-2 py-1 rounded border text-sm disabled:opacity-50',
                  isDark ? 'bg-gray-900 border-gray-700 text-white' : 'bg-white border-gray-300 text-gray-900',
                ]"
              />
            </label>
          </div>

          <div v-if="error" class="px-3 py-2 rounded-lg bg-red-600/15 text-red-400 text-sm">{{ error }}</div>
          <div v-if="result" :class="['px-3 py-2 rounded-lg text-sm', isDark ? 'bg-gray-900' : 'bg-gray-100']">
            已扫描 {{ result.scanned_files }} 个文件，新增 {{ result.added_count }} 项，已有 {{ result.existing_count }} 项，首帧 {{ result.thumbnail_count }} 张，预览 {{ result.preview_count }} 张。
          </div>
        </div>

        <footer :class="['px-4 py-3 border-t flex items-center justify-end gap-2', isDark ? 'border-gray-800' : 'border-gray-200']">
          <button
            @click="emit('close')"
            :class="['px-4 py-2 rounded-lg text-sm transition-colors', isDark ? 'text-gray-300 hover:bg-gray-800' : 'text-gray-600 hover:bg-gray-100']"
          >
            关闭
          </button>
          <button
            @click="submit"
            :disabled="!canImport"
            class="px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-500 transition-colors disabled:opacity-50"
          >
            {{ importing ? '导入中...' : '导入' }}
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>
