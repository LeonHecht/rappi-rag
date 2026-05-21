import { createClient, type SupabaseClient } from '@supabase/supabase-js'
import { isDemoMode, demoUser } from './demoMode'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string | undefined
const supabasePublishableKey = (import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ||
  import.meta.env.VITE_SUPABASE_ANON_KEY) as string | undefined

// In test mode, provide a minimal no-op client if env vars are not set,
// so unit tests that forget to mock don't crash the test collector.
function makeNoopClient(): SupabaseClient {
  return {
    auth: {
      getSession: async () => ({
        data: { session: isDemoMode ? { user: demoUser, access_token: null } : null },
        error: null,
      }),
      getUser: async () => ({
        data: { user: isDemoMode ? demoUser : null },
        error: null,
      }),
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
    from: () => {
      throw new Error('Supabase is not configured.')
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
    : isTest || isDemoMode
    ? makeNoopClient()
    : (() => {
        throw new Error('supabaseUrl is required.')
      })()
