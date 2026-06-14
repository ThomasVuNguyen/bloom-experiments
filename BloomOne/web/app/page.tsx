"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { LoginGate } from "@/components/login-gate";
import { Sidebar } from "@/components/sidebar";
import { Chat } from "@/components/chat";
import { PatientDetailPanel } from "@/components/patient-detail";
import { useChats } from "@/lib/use-chats";
import type { ChatMessage } from "@/lib/api";

function ChatApp() {
  const {
    chats,
    activeChat,
    activeChatId,
    createChat,
    updateChat,
    deleteChat,
    renameChat,
    selectChat,
    setActiveChatId,
  } = useChats();

  // Pre-warm the Modal backend on page load (fire-and-forget).
  // This wakes the container from cold sleep so the first chat
  // message doesn't hit a ~20s cold start.
  useEffect(() => {
    fetch("/api/warmup").catch(() => {
      // Silent fail — warmup is best-effort
    });
  }, []);


  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(
    null,
  );

  // Ref to synchronously track a just-created chat ID within the same render
  // cycle, preventing duplicate chat creation when handleMessagesChange is
  // called multiple times before React re-renders (user msg + assistant msg).
  const pendingChatIdRef = useRef<string | null>(null);

  // Per-chat LLM history (includes tool calls, not persisted to save space)
  const [llmHistoryMap, setLlmHistoryMap] = useState<
    Record<string, ChatMessage[]>
  >({});

  const currentMessages = activeChat?.messages || [];
  const currentLlmHistory = activeChatId
    ? llmHistoryMap[activeChatId] || currentMessages
    : [];

  const handleMessagesChange = useCallback(
    (messages: ChatMessage[]) => {
      let chatId = activeChatId || pendingChatIdRef.current;
      if (!chatId) {
        chatId = createChat();
        pendingChatIdRef.current = chatId;
      }
      updateChat(chatId, messages);
    },
    [activeChatId, createChat, updateChat],
  );

  const handleLlmHistoryChange = useCallback(
    (history: ChatMessage[]) => {
      const chatId = activeChatId || pendingChatIdRef.current;
      if (!chatId) return;
      setLlmHistoryMap((prev) => ({
        ...prev,
        [chatId]: history,
      }));
    },
    [activeChatId],
  );

  const handleNewChat = useCallback(() => {
    pendingChatIdRef.current = null;
    createChat();
    setSidebarOpen(false);
  }, [createChat]);

  const handleSelectChat = useCallback(
    (id: string) => {
      pendingChatIdRef.current = null;
      selectChat(id);
      setSelectedPatientId(null); // Close patient panel when switching chats
    },
    [selectChat],
  );

  const handleDeleteChat = useCallback(
    (id: string) => {
      deleteChat(id);
      setLlmHistoryMap((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
    },
    [deleteChat],
  );

  const handleSelectPatient = useCallback((id: string) => {
    setSelectedPatientId((prev) => (prev === id ? null : id)); // Toggle
  }, []);

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        chats={chats}
        activeChatId={activeChatId}
        onSelectChat={handleSelectChat}
        onNewChat={handleNewChat}
        onDeleteChat={handleDeleteChat}
        onRenameChat={renameChat}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onSelectPatient={handleSelectPatient}
        selectedPatientId={selectedPatientId}
        isCollapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
      />

      <Chat
        key={activeChatId || "new"}
        messages={currentMessages}
        onMessagesChange={handleMessagesChange}
        llmHistory={currentLlmHistory}
        onLlmHistoryChange={handleLlmHistoryChange}
        onSidebarToggle={() => setSidebarOpen(true)}
        chatTitle={activeChat?.title || null}
        isSidebarCollapsed={sidebarCollapsed}
        onExpandSidebar={() => setSidebarCollapsed(false)}
      />

      {/* Patient detail panel */}
      {selectedPatientId && (
        <div className="hidden lg:block w-80 xl:w-96 flex-shrink-0">
          <PatientDetailPanel
            key={selectedPatientId}
            patientId={selectedPatientId}
            onClose={() => setSelectedPatientId(null)}
          />
        </div>
      )}
    </div>
  );
}

export default function Home() {
  return (
    <LoginGate>
      <ChatApp />
    </LoginGate>
  );
}
