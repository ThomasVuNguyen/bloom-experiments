"use client";

import { useState, useEffect, useCallback } from "react";
import type { ChatMessage } from "@/lib/api";

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
}

const STORAGE_KEY = "bloomone_chats";

function generateId(): string {
  return `chat_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function loadChats(): ChatSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveChats(chats: ChatSession[]) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(chats));
  } catch {
    // Storage full — remove oldest chats
    const trimmed = chats.slice(-20);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  }
}

/** Derive a title from the first user message */
function deriveTitle(messages: ChatMessage[]): string {
  const first = messages.find((m) => m.role === "user");
  if (!first) return "New Chat";
  const text = first.content.replace(/\[.*?\]\s*/g, "").trim();
  return text.length > 60 ? text.slice(0, 57) + "..." : text;
}

export function useChats() {
  const [chats, setChats] = useState<ChatSession[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);

  // Load from localStorage on mount
  useEffect(() => {
    const loaded = loadChats();
    setChats(loaded);
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
    setChats((prev) => {
      const updated = [newChat, ...prev];
      saveChats(updated);
      return updated;
    });
    setActiveChatId(newChat.id);
    return newChat.id;
  }, []);

  const updateChat = useCallback(
    (chatId: string, messages: ChatMessage[]) => {
      setChats((prev) => {
        const updated = prev.map((c) =>
          c.id === chatId
            ? {
                ...c,
                messages,
                title: deriveTitle(messages),
                updatedAt: Date.now(),
              }
            : c,
        );
        saveChats(updated);
        return updated;
      });
    },
    [],
  );

  const deleteChat = useCallback(
    (chatId: string) => {
      setChats((prev) => {
        const updated = prev.filter((c) => c.id !== chatId);
        saveChats(updated);
        return updated;
      });
      if (activeChatId === chatId) {
        setActiveChatId(null);
      }
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
    createChat,
    updateChat,
    deleteChat,
    selectChat,
    setActiveChatId,
  };
}
