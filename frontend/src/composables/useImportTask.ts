import { cancelImport, fetchImportJobs, fetchImportProgress, importMediaFolder } from '../api/client'
import { createImportTaskController } from './importTaskController'

// crypto.randomUUID is unavailable on plain HTTP LAN origins; getRandomValues is.
function uuid() {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6]! & 15) | 64
  bytes[8] = (bytes[8]! & 63) | 128
  const hex = [...bytes].map(b => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

const task = createImportTaskController({
  list: fetchImportJobs, get: fetchImportProgress, start: importMediaFolder, cancel: cancelImport,
  storage: {
    getItem: key => localStorage.getItem(key),
    setItem: (key, value) => localStorage.setItem(key, value),
    removeItem: key => localStorage.removeItem(key),
  },
  storageKey: 'lanstream:import:/api/media:v1', uuid,
})

export function useImportTask() { return task }
