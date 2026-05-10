import { ref, watch } from 'vue'

const isDark = ref(localStorage.getItem('lanstream-theme') !== 'light')

watch(isDark, (val) => {
  localStorage.setItem('lanstream-theme', val ? 'dark' : 'light')
})

export function useTheme() {
  function toggleTheme() {
    isDark.value = !isDark.value
  }
  return { isDark, toggleTheme }
}
