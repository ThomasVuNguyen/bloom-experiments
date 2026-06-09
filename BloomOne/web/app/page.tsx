"use client";

import { useState, useCallback } from "react";
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

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(
    null,
  );

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
      let chatId = activeChatId;
      if (!chatId) {
        chatId = createChat();
      }
      updateChat(chatId, messages);
    },
    [activeChatId, createChat, updateChat],
  );

  const handleLlmHistoryChange = useCallback(
    (history: ChatMessage[]) => {
      if (!activeChatId) return;
      setLlmHistoryMap((prev) => ({
        ...prev,
        [activeChatId]: history,
      }));
    },
    [activeChatId],
  );

  const handleNewChat = useCallback(() => {
    createChat();
    setSidebarOpen(false);
  }, [createChat]);

  const handleSelectChat = useCallback(
    (id: string) => {
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
      />

      <Chat
        key={activeChatId || "new"}
        messages={currentMessages}
        onMessagesChange={handleMessagesChange}
        llmHistory={currentLlmHistory}
        onLlmHistoryChange={handleLlmHistoryChange}
        onSidebarToggle={() => setSidebarOpen(true)}
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
