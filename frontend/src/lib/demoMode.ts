const isTest =
  (import.meta as any)?.vitest ||
  import.meta.env.MODE === "test" ||
  (typeof process !== "undefined" && (process as any).env?.VITEST);

const missingSupabaseConfig =
  !import.meta.env.VITE_SUPABASE_URL ||
  !(import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || import.meta.env.VITE_SUPABASE_ANON_KEY);

export const isDemoMode =
  String(import.meta.env.VITE_DEMO_MODE || "").toLowerCase() === "true" ||
  String(import.meta.env.VITE_AUTH_DISABLED || "").toLowerCase() === "true" ||
  (!isTest && missingSupabaseConfig);

export const demoUser = {
  id: "demo-user",
  email: "demo@example.com",
  user_metadata: {
    full_name: "Demo User",
  },
};

export type DemoChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations?: Array<{ doc_id: string; snippet?: string }>;
  reasoning?: string[];
  reasoningStreaming?: boolean;
  reasoningStartedAt?: number;
  reasoningEndedAt?: number;
};

export type DemoChat = {
  id: string;
  title: string | null;
  created_at: string;
  updated_at?: string;
  messages?: DemoChatMessage[];
  agent_state?: string | null;
};

const STORAGE_KEY = "demo:chats";

function readChats(): DemoChat[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function writeChats(chats: DemoChat[]) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(chats));
  } catch {
    // Ignore storage failures; chat still works for the current render state.
  }
}

export function listDemoChats(): DemoChat[] {
  return readChats().sort((a, b) =>
    String(b.updated_at || b.created_at).localeCompare(String(a.updated_at || a.created_at))
  );
}

export function getDemoChat(id: string): DemoChat | undefined {
  return readChats().find((chat) => chat.id === id);
}

export function createDemoChat(title = "Nuevo chat"): DemoChat {
  const now = new Date().toISOString();
  const chat: DemoChat = {
    id: `demo-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    title,
    created_at: now,
    updated_at: now,
    messages: [],
    agent_state: null,
  };
  writeChats([chat, ...readChats()]);
  return chat;
}

export function updateDemoChat(id: string, patch: Partial<DemoChat>) {
  const now = new Date().toISOString();
  writeChats(
    readChats().map((chat) =>
      chat.id === id ? { ...chat, ...patch, updated_at: now } : chat
    )
  );
}

export function deleteDemoChat(id: string) {
  writeChats(readChats().filter((chat) => chat.id !== id));
}

export function appendDemoMessage(chatId: string, message: DemoChatMessage) {
  const now = new Date().toISOString();
  writeChats(
    readChats().map((chat) =>
      chat.id === chatId
        ? {
            ...chat,
            messages: [...(chat.messages || []), message],
            updated_at: now,
          }
        : chat
    )
  );
}
