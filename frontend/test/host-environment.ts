import type { Environment } from 'vitest/environments'

// Compile Vue SFCs for the client while their DOM operations are supplied by
// the component tests' custom renderer. No jsdom or browser dependency needed.
export default {
  name: 'host-renderer',
  viteEnvironment: 'client',
  setup() { return { teardown() {} } },
} satisfies Environment
