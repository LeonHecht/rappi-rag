import { useEffect, useState, useCallback } from "react";
import { supabase } from "@/lib/supabaseClient";
import {
  createDemoChat,
  deleteDemoChat,
  isDemoMode,
  listDemoChats,
  updateDemoChat,
} from "@/lib/demoMode";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MoreVertical } from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuAction,
} from "@/components/ui/sidebar"

import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu"

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog"

type Chat = {
  id: string;
  title: string | null;
  created_at: string;
  updated_at?: string;
};

export type ChatSidebarProps = {
  selectedId: string | null;
  onSelect: (id: string) => void;
  onCreated?: (id: string) => void;
  className?: string;
};

export default function ChatSidebar({
  selectedId,
  onSelect,
  onCreated,
  className,
}: ChatSidebarProps) {
  const [chats, setChats] = useState<Chat[]>([]);
  const [loading, setLoading] = useState(false);
  // Rename dialog state
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<Chat | null>(null);
  const [renameValue, setRenameValue] = useState("");
  // Delete confirm dialog state
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Chat | null>(null);

  const fetchChats = useCallback(async () => {
    setLoading(true);
    if (isDemoMode) {
      setChats(listDemoChats());
      setLoading(false);
      return;
    }
    const { data, error } = await supabase
      .from("chats")
      .select("id,title,created_at,updated_at")
      .order("updated_at", { ascending: false })
      .order("created_at", { ascending: false });
    if (!error && data) setChats(data as Chat[]);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchChats();
  }, [fetchChats]);

  // Listen for local UI events to keep list in sync without a full reload
  useEffect(() => {
    const handleChatUpdated = (e: Event) => {
      const evt = e as CustomEvent<{ id: string; title?: string }>; 
      const { id, title } = evt.detail || ({} as any);
      if (!id) return;
      setChats((prev) =>
        prev.map((c) => (c.id === id ? { ...c, title: title ?? c.title } : c))
      );
    };

    const handleChatCreated = (e: Event) => {
      const evt = e as CustomEvent<{ chat: Chat }>; 
      const chat = evt.detail?.chat;
      if (!chat) return;
      setChats((prev) => {
        if (prev.some((c) => c.id === chat.id)) return prev;
        return [chat, ...prev];
      });
    };

    window.addEventListener("chat:updated", handleChatUpdated as EventListener);
    window.addEventListener("chat:created", handleChatCreated as EventListener);
    return () => {
      window.removeEventListener(
        "chat:updated",
        handleChatUpdated as EventListener
      );
      window.removeEventListener(
        "chat:created",
        handleChatCreated as EventListener
      );
    };
  }, []);

  // Optional: subscribe to Supabase Realtime so updates from other tabs/processes also reflect instantly
  useEffect(() => {
    let channel: any;
    (async () => {
      if (isDemoMode) return;
      const {
        data: { user },
      } = await supabase.auth.getUser();
      if (!user) return;
      channel = supabase
        .channel("realtime:chats")
        .on(
          "postgres_changes",
          { event: "INSERT", schema: "public", table: "chats", filter: `user_id=eq.${user.id}` },
          (payload) => {
            const chat = payload.new as Chat;
            setChats((prev) => {
              if (prev.some((c) => c.id === chat.id)) return prev;
              return [chat, ...prev];
            });
          }
        )
        .on(
          "postgres_changes",
          { event: "UPDATE", schema: "public", table: "chats", filter: `user_id=eq.${user.id}` },
          (payload) => {
            const chat = payload.new as Chat;
            setChats((prev) =>
              prev.map((c) =>
                c.id === chat.id
                  ? { ...c, title: chat.title, updated_at: chat.updated_at }
                  : c
              )
            );
          }
        )
        .on(
          "postgres_changes",
          { event: "DELETE", schema: "public", table: "chats", filter: `user_id=eq.${user.id}` },
          (payload) => {
            const oldId = (payload.old as any)?.id as string | undefined;
            if (!oldId) return;
            setChats((prev) => prev.filter((c) => c.id !== oldId));
          }
        )
        .subscribe();
    })();

    return () => {
      if (channel) {
        try {
          supabase.removeChannel(channel);
        } catch {}
      }
    };
  }, []);

  const createChat = useCallback(async () => {
    if (isDemoMode) {
      const chat = createDemoChat();
      setChats((prev) => [chat, ...prev]);
      onCreated?.(chat.id);
      onSelect(chat.id);
      return;
    }
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (!user) return;

    const { data, error } = await supabase
      .from("chats")
      .insert({
        user_id: user.id,
        title: "Nuevo chat",
      })
      .select()
      .single();

    if (!error && data) {
      setChats((prev) => [data as Chat, ...prev]);
      onCreated?.(data.id);
      onSelect(data.id);
    }
  }, [onCreated, onSelect]);

  const openRename = (chat: Chat) => {
    setRenameTarget(chat);
    setRenameValue(chat.title || "");
    setRenameOpen(true);
  };

  const saveRename = async () => {
    if (!renameTarget) return;
    const newTitle = renameValue.trim() || "Sin título";
    if (isDemoMode) {
      updateDemoChat(renameTarget.id, { title: newTitle });
      setChats((prev) =>
        prev.map((c) => (c.id === renameTarget.id ? { ...c, title: newTitle } : c))
      );
      try {
        window.dispatchEvent(
          new CustomEvent("chat:updated", { detail: { id: renameTarget.id, title: newTitle } })
        );
      } catch {}
      setRenameOpen(false);
      setRenameTarget(null);
      return;
    }
    const { error } = await supabase
      .from("chats")
      .update({ title: newTitle })
      .eq("id", renameTarget.id);
    if (!error) {
      setChats((prev) =>
        prev.map((c) => (c.id === renameTarget.id ? { ...c, title: newTitle } : c))
      );
      try {
        window.dispatchEvent(
          new CustomEvent("chat:updated", { detail: { id: renameTarget.id, title: newTitle } })
        );
      } catch {}
      setRenameOpen(false);
      setRenameTarget(null);
    }
  };

  const openDelete = (chat: Chat) => {
    setDeleteTarget(chat);
    setDeleteOpen(true);
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    const id = deleteTarget.id;
    if (isDemoMode) {
      deleteDemoChat(id);
      setChats((prev) => prev.filter((c) => c.id !== id));
      setDeleteOpen(false);
      setDeleteTarget(null);
      return;
    }
    // Best-effort: delete messages first to avoid FK constraint issues, then the chat
    try {
      await supabase.from("chat_messages").delete().eq("chat_id", id);
    } catch {}
    const { error } = await supabase.from("chats").delete().eq("id", id);
    if (!error) {
      setChats((prev) => prev.filter((c) => c.id !== id));
      setDeleteOpen(false);
      setDeleteTarget(null);
    }
  };

  return (
    <Sidebar
      className={className}
      // Use CSS var with fallback, so it adapts to navbar height dynamically
      style={{
        top: "var(--navbar-h, 4rem)",
        height: "calc(100vh - var(--navbar-h, 4rem))",
      }}
    >
      {/* Keep header sticky so actions stay visible while scrolling */}
      <SidebarHeader className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
        <div className="flex items-center justify-between px-3 py-2">
          <span className="font-semibold">Chats</span>
          <div className="flex items-center gap-2">
            {/* Removed reload button as requested */}
            <Button size="sm" onClick={createChat} disabled={loading}>
              + Nuevo
            </Button>
          </div>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Historial de Chats</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {chats.map((c) => (
                <SidebarMenuItem key={c.id}>
                  <SidebarMenuButton
                    isActive={selectedId === c.id}
                    onClick={() => onSelect(c.id)}
                  >
                    <span className="truncate">{c.title || "Sin título"}</span>
                  </SidebarMenuButton>
                  {/* Actions */}
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <SidebarMenuAction
                        showOnHover
                        onClick={(e) => e.stopPropagation()}
                        aria-label="Opciones"
                      >
                        <MoreVertical className="size-4" />
                      </SidebarMenuAction>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-44">
                      <DropdownMenuItem onSelect={() => openRename(c)}>
                        Renombrar
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        onSelect={() => openDelete(c)}
                        className="text-red-600 focus:text-red-700"
                      >
                        Eliminar
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </SidebarMenuItem>
              ))}
              {chats.length === 0 && !loading && (
                <div className="px-3 py-2 text-sm text-muted-foreground">
                  No hay chats todavía.
                </div>
              )}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      {/* Rename Dialog */}
      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent onOpenAutoFocus={(e) => e.preventDefault()}>
          <DialogHeader>
            <DialogTitle>Cambiar título del chat</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <Input
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              placeholder="Nuevo título"
              autoFocus
            />
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <DialogClose asChild>
              <Button variant="outline">Cancelar</Button>
            </DialogClose>
            <Button onClick={saveRename}>Guardar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirm Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Eliminar chat</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            ¿Seguro que quieres eliminar este chat? Esta acción no se puede deshacer.
          </p>
          <DialogFooter className="gap-2 sm:gap-0">
            <DialogClose asChild>
              <Button variant="outline">Cancelar</Button>
            </DialogClose>
            <Button variant="destructive" onClick={confirmDelete}>
              Eliminar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Sidebar>
  );
}
