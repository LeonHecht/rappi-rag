import { useEffect, useRef, useState, useCallback } from "react";
import SpaceSelect from "@/components/SpaceSelect";
import ChatSidebar from "@/components/ChatSidebar";
import { apiFetch } from "@/hooks/useApi";
import { supabase } from "@/lib/supabaseClient";
import { SidebarProvider, SidebarTrigger, SidebarInset } from "@/components/ui/sidebar"

// AI Elements
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import { Message, MessageContent } from "@/components/ai-elements/message";
import { Response } from "@/components/ai-elements/response";
import MarkdownWithCitations from "@/components/MarkdownWithCitations";
import { Reasoning, ReasoningTrigger, ReasoningContent } from "@/components/ai-elements/reasoning";
import { Shimmer } from "@/components/ai-elements/shimmer";
import {
  InlineCitation,
  InlineCitationText,
  InlineCitationCard,
  InlineCitationCardTrigger,
  InlineCitationCardBody,
  InlineCitationCarousel,
  InlineCitationCarouselHeader,
  InlineCitationCarouselIndex,
  InlineCitationCarouselPrev,
  InlineCitationCarouselNext,
  InlineCitationCarouselContent,
  InlineCitationCarouselItem,
  InlineCitationSource,
  InlineCitationQuote,
} from "@/components/ai-elements/inline-citation";
import {
  PromptInput,
  PromptInputBody,
  PromptInputTextarea,
  PromptInputFooter,
  PromptInputTools,
  PromptInputSubmit,
} from "@/components/ai-elements/prompt-input";

type ChatMsg = {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations?: Array<{ doc_id: string; snippet?: string }>;
  reasoning?: string[];
  reasoningStreaming?: boolean;
};

export default function Chat() {
  // Avoid double slashes when VITE_API_BASE ends with '/'
  const API_BASE = (import.meta.env.VITE_API_BASE || "http://localhost:8000").replace(/\/+$/, "");

  const [title, setTitle] = useState<string>("");
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [spaces, setSpaces] = useState<string[]>([]);
  const [space, setSpace] = useState<string>("");
  const [agentState, setAgentState] = useState<string | null>(null);
  const [text, setText] = useState<string>("");
  const [status, setStatus] = useState<"ready" | "submitted" | "streaming">(
    "ready"
  );
  const [currentChatId, setCurrentChatId] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const useStreaming: boolean = true;

  const token = (() => {
    try {
      const raw = localStorage.getItem("auth");
      return raw ? (JSON.parse(raw).token as string) : null;
    } catch {
      return null;
    }
  })();

  useEffect(() => {
    let alive = true;
    apiFetch("user/spaces")
      .then((d) => {
        if (!alive) return;
        const s: string[] = d.spaces || [];
        setSpaces(s);
        if (s.length > 0) setSpace((prev) => prev || s[0]);
      })
      .catch((e) => console.error("Failed to fetch spaces", e));
    return () => {
      alive = false;
    };
  }, []);

  function scrollMessageToTop(messageId: string) {
    const container = scrollContainerRef.current;
    if (!container) return;

    const target = container.querySelector(
      `[data-message-id="${CSS.escape(messageId)}"]`
    ) as HTMLElement | null;
    if (!target) return;

    const top =
      target.getBoundingClientRect().top -
      container.getBoundingClientRect().top +
      container.scrollTop;

    try {
      // instant jump; change to 'smooth' if you prefer animation
      container.scrollTo({ top, behavior: "auto" });
    } catch {
      container.scrollTop = top;
    }
  }

  // After a new user message is rendered, align it to the top of the scroll container
  useEffect(() => {
    if (messages.length === 0) return;
    const last = messages[messages.length - 1];
    if (last.role !== "user") return;

    const id = window.setTimeout(() => {
      scrollMessageToTop(last.id);
    }, 0);

    return () => window.clearTimeout(id);
  }, [messages]);

  function pushMessage(
    role: "user" | "assistant",
    text: string,
    citations: ChatMsg["citations"] = []
  ) {
    setMessages((prev) => [
      ...prev,
      { id: `${Date.now()}-${prev.length}`, role, text, citations },
    ]);
  }

  const loadChatMessages = useCallback(async (chatId: string) => {
    const { data, error } = await supabase
      .from("chat_messages")
      .select("id, role, content, meta")
      .eq("chat_id", chatId)
      .order("created_at", { ascending: true });

    if (!error && data) {
      setMessages(
        (data as any[]).map((m) => ({
          id: m.id,
          role: m.role,
          text: m.content as string,
          citations: m.meta?.citations || [],
          reasoning: m.meta?.reasoning || [],
          reasoningStreaming: false,
        }))
      );
    }
  }, []);

  const loadChatAgentState = useCallback(async (chatId: string) => {
    const { data, error } = await supabase
      .from("chats")
      .select("agent_state")
      .eq("id", chatId)
      .single();

    if (!error && data) {
      const st = (data as any).agent_state;
      if (st == null) {
        setAgentState(null);
      } else if (typeof st === "string") {
        setAgentState(st);
      } else {
        try {
          setAgentState(JSON.stringify(st));
        } catch {
          setAgentState(null);
        }
      }
    }
  }, []);

  async function ensureChat(title: string) {
    if (currentChatId) return currentChatId;
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (!user) throw new Error("Necesitas iniciar sesión");

    const { data, error } = await supabase
      .from("chats")
      .insert({ user_id: user.id, title })
      .select()
      .single();
    if (error) throw error;

    setCurrentChatId(data.id as string);
    // Notify sidebar immediately about the newly created chat so it appears without reload
    try {
      window.dispatchEvent(
        new CustomEvent("chat:created", { detail: { chat: data } })
      );
    } catch (e) {
      // no-op: event dispatch is best-effort
    }
    return data.id as string;
  }

  function pushAssistantPlaceholder() {
    const id = `${Date.now()}-assistant`;
    setMessages((prev) => [
      ...prev,
      { id, role: "assistant", text: "", reasoning: [], reasoningStreaming: true },
    ]);
    return id;
  }

  function appendAssistantDelta(assistantId: string, delta: string) {
    setMessages((prev) =>
      prev.map((m) =>
      m.id === assistantId ? { ...m, text: (m.text || "") + delta } : m
      )
    );
  }

  function finalizeAssistant(assistantId: string, fullText: string, citations?: ChatMsg["citations"]) {
    setMessages((prev) =>
        prev.map((m) =>
        m.id === assistantId ? { ...m, text: fullText, citations: citations || [] } : m
        )
    );
  }

  function addReasoningLine(assistantId: string, line: string) {
    setMessages((prev) =>
      prev.map((m) => {
        if (m.id !== assistantId) return m;
        const existing = m.reasoning || [];
        if (existing.includes(line)) return m;
        return { ...m, reasoning: [...existing, line], reasoningStreaming: true };
      })
    );
  }

  function setMessageReasoningStreaming(assistantId: string, streaming: boolean) {
    setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, reasoningStreaming: streaming } : m)));
  }

  function finishReasoningNow(assistantId: string) {
    // Mark reasoning as finished and set a duration immediately based on start time
    setMessages((prev) =>
      prev.map((m) => {
        if (m.id !== assistantId) return m;
        if (!m.reasoningStreaming) return m; // already finished
        return {
          ...m,
          reasoningStreaming: false,
        };
      })
    );
  }

    async function handleSubmitNonStream(trimmed: string) {
        // Ensure we have a chat ID, creating one if needed
        const chatId = await ensureChat(trimmed.slice(0, 60));

        // user message (UI + persist)
        pushMessage("user", trimmed);
        setText("");
        await supabase.from("chat_messages").insert({
            chat_id: chatId, role: "user", content: trimmed, meta: null,
        });

        const res = await fetch(`${API_BASE}/v1/chat/agentic`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
            body: JSON.stringify({ space, messages: [{ role: "user", content: trimmed }], state: agentState || null }),
        });
        if (!res.ok) throw new Error(`agentic ${res.status}`);
        const data = await res.json();

        if (data.title) {
            setTitle(data.title);
            await supabase.from("chats").update({ title: data.title }).eq("id", chatId);
            try { window.dispatchEvent(new CustomEvent("chat:updated", { detail: { id: chatId, title: data.title } })); } catch {}
        }
        if (data.agent_state) {
            setAgentState(data.agent_state);
            await supabase.from("chats").update({ agent_state: data.agent_state }).eq("id", chatId);
        }

        await supabase.from("chat_messages").insert({
            chat_id: chatId, role: "assistant", content: data.answer || "", meta: { citations: data.citations || [] },
        });
        pushMessage("assistant", data.answer || "", data.citations || []);
    }

  async function handleSubmitStream(trimmed: string) {
    const chatId = await ensureChat(trimmed.slice(0, 60));

    // user message (UI + persist)
    pushMessage("user", trimmed);
    setText("");
    await supabase.from("chat_messages").insert({
        chat_id: chatId, role: "user", content: trimmed, meta: null,
    });

    // assistant placeholder (we'll stream into it)
    const assistantId = pushAssistantPlaceholder();
    
    // Prepare abort controller so we can cancel mid-stream
    const controller = new AbortController();
    abortRef.current = controller;
    setStatus("streaming");
    
    // Local buffer to persist reasoning lines for this assistant turn
    const reasoningBuf: string[] = [];

    let res: Response;
    try {
      res = await fetch(`${API_BASE}/v1/chat/agentic/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ space, messages: [{ role: "user", content: trimmed }], state: agentState || null }),
        signal: controller.signal,
      });
    } catch (err: any) {
      if (err?.name === "AbortError") {
        // User cancelled before response; just reset state
        setStatus("ready");
        abortRef.current = null;
        return;
      }
      throw err;
    }
    if (!res.ok || !res.body) {
      throw new Error(`agentic/stream ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const handleFrame = async (event: string, dataStr: string) => {
      let payload: any = {};
      try { payload = dataStr ? JSON.parse(dataStr) : {}; } catch {}

      switch (event) {
        case "response.emit_message": {
          const msg = payload.msg || "Pensando";
          // Attach emitted reasoning message to the current assistant message
          addReasoningLine(assistantId, msg);
          reasoningBuf.push(msg);
                  break;
        }
        case "response.output_text.delta": {
            const delta = payload.delta || "";
            appendAssistantDelta(assistantId, delta);
            // As soon as the assistant starts typing, stop thinking and show duration immediately
            finishReasoningNow(assistantId);
            break;
        }
        case "response.output_text.done": {
            // optional: nothing; we’ll finalize on response.completed
            break;
        }
        case "response.completed": {
            const answer = payload.answer ?? "";
            const citations = payload.citations ?? [];
            const title = payload.title ?? "";
            const newState = payload.agent_state ?? null;

            finalizeAssistant(assistantId, answer, citations);

            if (title) {
                setTitle(title);
                await supabase.from("chats").update({ title }).eq("id", chatId);
                try { window.dispatchEvent(new CustomEvent("chat:updated", { detail: { id: chatId, title } })); } catch {}
            }
            if (newState) {
                setAgentState(newState);
                await supabase.from("chats").update({ agent_state: newState }).eq("id", chatId);
            }

            await supabase.from("chat_messages").insert({
                      chat_id: chatId, role: "assistant", content: answer, meta: { citations, reasoning: reasoningBuf },
            });

            setStatus("ready");
            // Streaming finished; allow Reasoning to auto-close for this message
            setMessageReasoningStreaming(assistantId, false);
            break;
        }

        // (optional) show trace / reasoning in a side panel if you want:
        case "reasoning.summary":
        case "reasoning.text":
        case "reasoning.summary_part":
        case "tool.start":
        case "tool.result":
        case "trace":
            // you can dispatch to a debug pane here
            break;
        }
    };

    // basic SSE parsing: frames separated by \n\n, lines: "event: ..." and "data: ..."
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let sepIdx;
        while ((sepIdx = buffer.indexOf("\n\n")) !== -1) {
          const frame = buffer.slice(0, sepIdx);
          buffer = buffer.slice(sepIdx + 2);

          let evt: string | null = null;
          let dataStr = "";

          for (const line of frame.split("\n")) {
            if (line.startsWith("event:")) evt = line.slice(6).trim();
            else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
          }
          if (evt) await handleFrame(evt, dataStr);
        }
      }
    } catch (err: any) {
      if (err?.name === "AbortError") {
        // User-initiated cancellation; leave the partial assistant message as-is.
      } else {
        throw err;
      }
    } finally {
      // safety: if stream ended (naturally or aborted) without response.completed, mark ready
      setStatus("ready");
      abortRef.current = null;
      // Ensure reasoning collapses if we didn't receive response.completed
      setMessageReasoningStreaming(assistantId, false);
    }
  }

  async function handleSubmit() {
    const trimmed = text.trim();
    if (!trimmed || status !== "ready") return;
    setStatus("submitted");
    try {
      if (useStreaming) {
        await handleSubmitStream(trimmed);
      } else {
        await handleSubmitNonStream(trimmed);
      }
    } catch (err) {
        console.error("submit error", err);
        pushMessage("assistant", "Ocurrió un error procesando tu consulta.");
    } finally {
      if (!useStreaming) setStatus("ready"); // streaming sets status itself
    }
  }

  function stopStreaming() {
  try {
    abortRef.current?.abort();
  } catch {}
  }

  return (
    <SidebarProvider className="min-h-0 h-full w-full overflow-hidden">
      {/* Sidebar (fixed) + inset content. Using SidebarInset prevents double sidebar and handles the gap. */}
      <ChatSidebar
        className="shrink-0"
        selectedId={currentChatId}
        onSelect={(id) => {
          setCurrentChatId(id);
          loadChatMessages(id);
          loadChatAgentState(id);
        }}
        onCreated={(id) => {
          setCurrentChatId(id);
          setMessages([]);
          setAgentState(null);
        }}
      />

      {/* Main content inside the SidebarInset so it accounts for the sidebar gap */}
      <SidebarInset className="flex flex-col flex-1 min-h-0 min-w-0 overflow-hidden bg-[#F5F5F7]">
          {/* Sidebar toggle + Space selector (sticky below navbar) */}
          <div className="flex items-center gap-4 p-4">
            <SidebarTrigger />
            <SpaceSelect
              value={space}
              onChange={(v) => setSpace(v)}
              className="ml-1"
            />
          </div>

          {/* Messages area - scrollable content */}
          <div className="flex flex-col flex-1 min-h-0 overflow-hidden">
            <div
              className={`flex-1 min-h-0 overflow-y-auto px-3 pt-2 ${
                messages.length > 0 ? "pb-24" : "pb-6"
              }`}
              ref={scrollContainerRef}
            >
              <div className="mx-auto w-full max-w-4xl">
              <Conversation>
                <ConversationContent>
                  {messages.length === 0 ? (
                    <div className="flex items-center justify-center min-h-[50vh]">
                      <div className="text-center text-2xl text-gray-600">
                        Hola, ¿cómo puedo ayudarte hoy?
                      </div>
                    </div>
                  ) : (
                    messages.map((m) => (
                      <Message key={m.id} from={m.role} data-message-id={m.id}>
                        <MessageContent>
                          {m.role === "assistant" && m.reasoning && m.reasoning.length > 0 && (
                            <div className="mb-3">
                              <Reasoning
                                isStreaming={!!m.reasoningStreaming}
                                defaultOpen={!!m.reasoningStreaming}
                              >
                                <ReasoningTrigger />
                                <ReasoningContent>{m.reasoning.join("\n\n")}</ReasoningContent>
                              </Reasoning>
                            </div>
                          )}
                          {m.role === "assistant" && status === "streaming" && (!m.reasoning || m.reasoning.length === 0) && (m.text ?? "") === "" && (
                            <div className="mb-3 text-muted-foreground text-sm">
                              <Shimmer duration={2} spread={4}>Iniciando…</Shimmer>
                            </div>
                          )}
                          {m.role === "assistant" ? (
                            <MarkdownWithCitations
                              className="prose prose-slate max-w-none"
                              text={m.text}
                              citations={m.citations || []}
                              apiBase={API_BASE}
                            />
                          ) : (
                            <Response>{m.text}</Response>
                          )}
                        </MessageContent>
                      </Message>
                    ))
                  )}
                </ConversationContent>
                <ConversationScrollButton />
              </Conversation>
              </div>
            </div>
            {/* Input fixed at bottom of screen */}
            {/* <Textarea className="bg-white w-full max-w-2xl mx-auto shrink-0" placeholder="Type your message here." /> */}
            {/* <div className="fixed bottom-0 left-0 right-0 bg-[#F5F5F7] pb-3"> */}
            <div className="mx-auto max-w-3xl w-full shrink-0 px-3 pb-3">
              <PromptInput
                onSubmit={handleSubmit}
                className="bg-white rounded-2xl shadow-lg transition-colors hover:bg-gray-50"
              >
                <PromptInputBody>
                  <PromptInputTextarea
                    ref={textareaRef}
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    placeholder="Pregunta lo que quieras a tu asistente RAG..."
                  />
                </PromptInputBody>
                <PromptInputFooter>
                  <PromptInputTools />
                  <PromptInputSubmit
                    disabled={status === "submitted" || (status !== "streaming" && !text)}
                    status={status}
                    onClick={(e) => {
                      if (status === "streaming") {
                        e.preventDefault();
                        stopStreaming();
                      }
                    }}
                  />
                </PromptInputFooter>
              </PromptInput>
            </div>
          </div>
      </SidebarInset>
      {/* </div> */}
    </SidebarProvider>
  );
}
