"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type { ChatMessage } from "@/lib/api";

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
}

function generateId(): string {
  return `chat_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

/** Derive a title from the first user message */
function deriveTitle(messages: ChatMessage[]): string {
  const first = messages.find((m) => m.role === "user");
  if (!first) return "New Chat";
  const text = first.content.replace(/\[.*?\]\s*/g, "").trim();
  return text.length > 60 ? text.slice(0, 57) + "..." : text;
}

/** Debounced save to server */
function useDebouncedSave(delay = 500) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const save = useCallback(
    (chat: ChatSession) => {
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(async () => {
        try {
          await fetch("/api/chats", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(chat),
          });
        } catch {
          // Silent fail — chats still work in memory
        }
      }, delay);
    },
    [delay],
  );

  return save;
}

export function useChats() {
  const [chats, setChats] = useState<ChatSession[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const debouncedSave = useDebouncedSave();

  // Load from server on mount
  useEffect(() => {
    async function load() {
      try {
        const res = await fetch("/api/chats");
        if (res.ok) {
          const data = await res.json();
          setChats(data);
        }
      } catch {
        // API not available — start fresh
      } finally {
        setLoaded(true);
      }
    }
    load();
  }, []);

  const activeChat = chats.find((c) => c.id === activeChatId) || null;

  const createChat = useCallback((): string => {
    const newChat: ChatSession = {
      id: generateId(),
      title: "New Chat",
      messages: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    setChats((prev) => [newChat, ...prev]);
    setActiveChatId(newChat.id);
    debouncedSave(newChat);
    return newChat.id;
  }, [debouncedSave]);

  const updateChat = useCallback(
    (chatId: string, messages: ChatMessage[]) => {
      setChats((prev) => {
        const updated = prev.map((c) => {
          if (c.id !== chatId) return c;
          const patched = {
            ...c,
            messages,
            title: deriveTitle(messages),
            updatedAt: Date.now(),
          };
          debouncedSave(patched);
          return patched;
        });
        return updated;
      });
    },
    [debouncedSave],
  );

  const deleteChat = useCallback(
    (chatId: string) => {
      setChats((prev) => prev.filter((c) => c.id !== chatId));
      if (activeChatId === chatId) {
        setActiveChatId(null);
      }
      // Delete from server
      fetch(`/api/chats/${chatId}`, { method: "DELETE" }).catch(() => {});
    },
    [activeChatId],
  );

  const selectChat = useCallback((chatId: string) => {
    setActiveChatId(chatId);
  }, []);

  return {
    chats,
    activeChat,
    activeChatId,
    loaded,
    createChat,
    updateChat,
    deleteChat,
    selectChat,
    setActiveChatId,
  };
}
