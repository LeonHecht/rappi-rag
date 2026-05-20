import { createClient, type SupabaseClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string | undefined
const supabasePublishableKey = (import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ||
  import.meta.env.VITE_SUPABASE_ANON_KEY) as string | undefined

// In test mode, provide a minimal no-op client if env vars are not set,
// so unit tests that forget to mock don't crash the test collector.
function makeTestClient(): SupabaseClient {
  return {
    auth: {
      getSession: async () => ({ data: { session: null }, error: null }),
      onAuthStateChange: () => ({
        data: {
          subscription: {
            id: 'test-sub',
            callback: () => {},
            unsubscribe: () => {},
          },
        },
        error: null,
      }),
      signOut: async () => ({ error: null }),
    },
  } as unknown as SupabaseClient
}

const isTest =
  (import.meta as any)?.vitest ||
  import.meta.env.MODE === 'test' ||
  (typeof process !== 'undefined' && (process as any).env?.VITEST)

export const supabase: SupabaseClient =
  supabaseUrl && supabasePublishableKey
    ? createClient(supabaseUrl, supabasePublishableKey)
    : isTest
    ? makeTestClient()
    : (() => {
        throw new Error('supabaseUrl is required.')
      })()
