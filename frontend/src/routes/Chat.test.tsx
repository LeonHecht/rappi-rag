import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

// Mock Response component to avoid streamdown complexity
vi.mock('@/components/ai-elements/response', () => ({ 
  Response: ({ children }: any) => <div>{children}</div> 
}))

import Chat from './Chat'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------
// Mock supabase client with minimal behaviors the Chat route relies on.
vi.mock('@/lib/supabaseClient', () => {
  // Builder factory for supabase.from(<table>) chains
  const builder = (table: string) => {
    return {
      // Selection queries
      select() { return this },
      order() { return Promise.resolve({ data: [], error: null }) },
      eq() { return this },
      single() { // Used after chats.insert.select().single() and chats.select().single()
        if (table === 'chats') {
          return Promise.resolve({ data: { id: 'chat1', agent_state: null, title: 'chat1' }, error: null })
        }
        return Promise.resolve({ data: { agent_state: null }, error: null })
      },
      insert() { // chats.insert(...).select().single(); chat_messages.insert(...)
        if (table === 'chats') {
          return { select() { return this }, single: this.single }
        }
        // chat_messages insert returns a resolved object
        return Promise.resolve({ data: null, error: null })
      },
      update() { return Promise.resolve({ data: null, error: null }) },
      delete() { return Promise.resolve({ data: null, error: null }) },
    }
  }
  return {
    supabase: {
      auth: {
        getUser: vi.fn().mockResolvedValue({ data: { user: { id: 'u1' } } }),
        getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      },
      from: (table: string) => builder(table),
    },
  }
})

// Ensure SpaceSelect (used at top of Chat) is light weight.
vi.mock('@/components/SpaceSelect', () => ({ default: (props: any) => <select aria-label="space-select" value={props.value} onChange={e => props.onChange(e.target.value)} /> }))

// Mock Sidebar + related UI to avoid Radix complexity for unit tests.
vi.mock('@/components/ChatSidebar', () => ({ default: (props: any) => <div data-testid="chat-sidebar">Sidebar sel:{props.selectedId || 'none'}</div> }))
vi.mock('@/components/ui/sidebar', () => ({
  SidebarProvider: ({ children }: any) => <div data-testid="sidebar-provider">{children}</div>,
  SidebarTrigger: (p: any) => <button type="button" {...p}>Trigger</button>,
  SidebarInset: ({ children, className }: any) => <div className={className}>{children}</div>,
}))

// Lightweight MarkdownWithCitations to just render text
vi.mock('@/components/MarkdownWithCitations', () => ({
  default: ({ text }: { text: string }) => <div>{text}</div>,
}))

// AI elements minimal mocks
vi.mock('@/components/ai-elements/conversation', () => ({
  Conversation: ({ children }: any) => <div>{children}</div>,
  ConversationContent: ({ children }: any) => <div>{children}</div>,
  ConversationScrollButton: () => null,
}))
vi.mock('@/components/ai-elements/message', () => ({
  Message: ({ children, from, ...rest }: any) => <div data-role={from} {...rest}>{children}</div>,
  MessageContent: ({ children }: any) => <div>{children}</div>,
}))
vi.mock('@/components/ai-elements/response', () => ({ Response: ({ children }: any) => <div>{children}</div> }))
vi.mock('@/components/ai-elements/reasoning', () => ({
  Reasoning: ({ children, duration, isStreaming, message }: any) => (
    <div
      data-testid="reasoning"
      data-duration={duration}
      data-message={message}
      data-streaming={String(isStreaming)}
    >
      {children}
    </div>
  ),
  ReasoningTrigger: () => null,
  ReasoningContent: ({ children }: any) => <div>{children}</div>,
}))
vi.mock('@/components/ai-elements/shimmer', () => ({ Shimmer: ({ children }: any) => <span>{children}</span> }))
vi.mock('@/components/ai-elements/inline-citation', () => ({ InlineCitation: () => null }))
vi.mock('@/components/ai-elements/prompt-input', async () => {
  const real = await vi.importActual<any>('@/components/ai-elements/prompt-input')
  // Re-export real PromptInput* components (they are pure) but keep as-is
  return real
})

// Utility to build a mock ReadableStream for SSE frames.
function sseStream(frames: { event: string, data: any }[]) {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const f of frames) {
        const chunk = `event:${f.event}\ndata:${JSON.stringify(f.data)}\n\n`
        controller.enqueue(encoder.encode(chunk))
      }
      controller.close()
    },
  })
}

function rawStream(chunks: string[]) {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
}

// Reset fetch mock between tests
beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string, init?: any) => {
    if (url.includes('/v1/chat/agentic/stream')) {
      return Promise.resolve({
        ok: true,
        body: sseStream([
          { event: 'response.output_text.delta', data: { delta: 'Hola asistente' } },
          { event: 'response.completed', data: { answer: 'Hola asistente', citations: [] } },
        ]),
      }) as any
    }
    if (url.includes('/v1/user/spaces')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ spaces: ['public'] }) }) as any
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) }) as any
  }))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('Chat route component', () => {
  it('renders initial placeholder', async () => {
    render(<MemoryRouter><Chat /></MemoryRouter>)
    // Wait for initial effect (spaces fetch) to settle
    expect(await screen.findByText(/Hola, ¿cómo puedo ayudarte hoy?/)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Pregunta lo que quieras/)).toBeInTheDocument()
  })

  it('streams an assistant reply after submitting a user message', async () => {
    render(<MemoryRouter><Chat /></MemoryRouter>)
    const textarea = screen.getByPlaceholderText(/Pregunta lo que quieras/)
    await userEvent.type(textarea, 'Hola')
    const submitBtn = screen.getByRole('button', { name: /submit/i })
    await userEvent.click(submitBtn)

    // User message should appear (as plain text Response)
    await screen.findByText('Hola')

    // Assistant streamed reply should appear (same text after frames processed)
    await waitFor(() => {
      // We expect at least one assistant message container with final text
      const msgs = screen.getAllByText('Hola asistente')
      expect(msgs.length).toBeGreaterThan(0)
    })
  })

  it('handles chunked CRLF SSE and updates reasoning live', async () => {
    vi.mocked(fetch).mockImplementation((url: string) => {
      if (url.includes('/v1/chat/agentic/stream')) {
        return Promise.resolve({
          ok: true,
          body: rawStream([
            'event: response.emit_message\r\n',
            'data: {"msg":"Buscando documentos"}\r\n\r\n',
            'event: response.output_text.delta\r\n',
            'data: {"delta":"Hola"}\r\n\r\n',
            'event: response.output_text.delta\r\n',
            'data: {"delta":" en vivo"}\r\n\r\n',
            'event: response.completed\r\n',
            'data: {"citations":[]}\r\n\r\n',
          ]),
        }) as any
      }
      if (url.includes('/v1/user/spaces')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ spaces: ['public'] }) }) as any
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) }) as any
    })

    render(<MemoryRouter><Chat /></MemoryRouter>)
    const textarea = screen.getByPlaceholderText(/Pregunta lo que quieras/)
    await userEvent.type(textarea, 'Hola')
    await userEvent.click(screen.getByRole('button', { name: /submit/i }))

    await screen.findByText('Buscando documentos')
    expect(screen.getByTestId('reasoning')).toHaveAttribute('data-message', 'Buscando documentos')
    await screen.findByText('Hola en vivo')
    await waitFor(() => {
      expect(screen.getByTestId('reasoning')).toHaveAttribute('data-streaming', 'false')
      expect(screen.getByTestId('reasoning')).toHaveAttribute('data-duration', '1')
    })
  })
})
