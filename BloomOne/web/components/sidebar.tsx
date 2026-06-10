"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import type { ChatSession } from "@/lib/use-chats";
import { PatientList } from "@/components/patient-list";

interface SidebarProps {
  chats: ChatSession[];
  activeChatId: string | null;
  onSelectChat: (id: string) => void;
  onNewChat: () => void;
  onDeleteChat: (id: string) => void;
  onRenameChat: (id: string, title: string) => void;
  isOpen: boolean;
  onClose: () => void;
  onSelectPatient: (id: string) => void;
  selectedPatientId: string | null;
}

function formatTime(ts: number): string {
  const now = Date.now();
  const diff = now - ts;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(ts).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function ChatItem({
  chat,
  isActive,
  onSelect,
  onDelete,
  onRename,
}: {
  chat: ChatSession;
  isActive: boolean;
  onSelect: () => void;
  onDelete: () => void;
  onRename: (title: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(chat.title);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  const commitRename = useCallback(() => {
    const trimmed = editValue.trim();
    if (trimmed && trimmed !== chat.title) {
      onRename(trimmed);
    }
    setEditing(false);
  }, [editValue, chat.title, onRename]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter") {
        e.preventDefault();
        commitRename();
      } else if (e.key === "Escape") {
        setEditValue(chat.title);
        setEditing(false);
      }
    },
    [commitRename, chat.title],
  );

  if (editing) {
    return (
      <div
        className="w-full px-3 py-2.5 rounded-lg text-sm bg-secondary"
      >
        <input
          ref={inputRef}
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onBlur={commitRename}
          onKeyDown={handleKeyDown}
          className="w-full bg-transparent text-foreground outline-none 
                   border-b border-primary pb-0.5 text-sm"
          maxLength={80}
        />
        <span className="text-[10px] text-muted-foreground mt-1 block">
          Enter to save · Esc to cancel
        </span>
      </div>
    );
  }

  return (
    <button
      onClick={onSelect}
      onDoubleClick={(e) => {
        e.preventDefault();
        setEditValue(chat.title);
        setEditing(true);
      }}
      className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all duration-150 group
        ${
          isActive
            ? "bg-secondary text-foreground border-l-2 border-primary"
            : "text-secondary-foreground hover:bg-secondary/50 hover:text-foreground"
        }`}
    >
      <div className="flex items-start justify-between gap-1">
        <span className="truncate leading-snug flex-1">{chat.title}</span>
        <div className="flex-shrink-0 flex items-center gap-0.5 opacity-0 group-hover:opacity-100">
          {/* Rename button */}
          <button
            onClick={(e) => {
              e.stopPropagation();
              setEditValue(chat.title);
              setEditing(true);
            }}
            className="text-muted-foreground hover:text-primary transition-colors p-0.5 rounded hover:bg-primary/10"
            title="Rename chat"
          >
            <svg
              className="w-3.5 h-3.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10"
              />
            </svg>
          </button>
          {/* Delete button */}
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="text-muted-foreground hover:text-destructive transition-colors p-0.5 rounded hover:bg-destructive/10"
            title="Delete chat"
          >
            <svg
              className="w-3.5 h-3.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>
      </div>
      <span className="text-[10px] text-muted-foreground mt-0.5 block">
        {formatTime(chat.updatedAt)}
      </span>
    </button>
  );
}

export function Sidebar({
  chats,
  activeChatId,
  onSelectChat,
  onNewChat,
  onDeleteChat,
  onRenameChat,
  isOpen,
  onClose,
  onSelectPatient,
  selectedPatientId,
}: SidebarProps) {
  const [activeTab, setActiveTab] = useState<"chats" | "patients">("chats");

  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/30 z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={`fixed lg:static inset-y-0 left-0 z-50 w-72 
                   bg-card border-r border-border
                   flex flex-col transition-transform duration-300 ease-in-out
                   ${isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <div className="flex items-center gap-2">
            <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-7 h-7">
              <circle cx="16" cy="13" r="4" fill="var(--primary)" opacity="0.9"/>
              <ellipse cx="10.5" cy="15.5" rx="3.5" ry="4.5" transform="rotate(-30 10.5 15.5)" fill="var(--primary)" opacity="0.6"/>
              <ellipse cx="21.5" cy="15.5" rx="3.5" ry="4.5" transform="rotate(30 21.5 15.5)" fill="var(--primary)" opacity="0.6"/>
              <ellipse cx="12" cy="20" rx="3.5" ry="4.5" transform="rotate(-60 12 20)" fill="var(--primary)" opacity="0.45"/>
              <ellipse cx="20" cy="20" rx="3.5" ry="4.5" transform="rotate(60 20 20)" fill="var(--primary)" opacity="0.45"/>
              <circle cx="16" cy="16" r="2.5" fill="var(--accent)"/>
              <rect x="15.25" y="20" width="1.5" height="8" rx="0.75" fill="var(--primary)" opacity="0.7"/>
            </svg>
            <span className="text-sm font-serif font-semibold text-foreground">
              BloomOne
            </span>
          </div>
          {activeTab === "chats" && (
            <button
              onClick={onNewChat}
              className="p-1.5 rounded-lg border border-primary text-primary 
                         hover:bg-primary hover:text-primary-foreground transition-colors"
              title="New chat"
            >
              <svg
                className="w-4 h-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 4.5v15m7.5-7.5h-15"
                />
              </svg>
            </button>
          )}
        </div>

        {/* Tabs */}
        <div className="flex border-b border-border">
          <button
            onClick={() => setActiveTab("chats")}
            className={`flex-1 px-3 py-2 text-xs font-medium transition-colors flex items-center justify-center gap-1.5
              ${activeTab === "chats"
                ? "text-primary border-b-2 border-primary"
                : "text-muted-foreground hover:text-foreground"}`}
          >
            {/* Speech bubble icon */}
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            Chats
          </button>
          <button
            onClick={() => setActiveTab("patients")}
            className={`flex-1 px-3 py-2 text-xs font-medium transition-colors flex items-center justify-center gap-1.5
              ${activeTab === "patients"
                ? "text-primary border-b-2 border-primary"
                : "text-muted-foreground hover:text-foreground"}`}
          >
            {/* People icon */}
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
            </svg>
            Patients
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5">
          {activeTab === "chats" ? (
            <>
              {chats.length === 0 && (
                <p className="text-xs text-muted-foreground text-center py-8 px-4">
                  No chats yet. Start a new conversation!
                </p>
              )}

              {chats.map((chat) => (
                <ChatItem
                  key={chat.id}
                  chat={chat}
                  isActive={chat.id === activeChatId}
                  onSelect={() => {
                    onSelectChat(chat.id);
                    onClose();
                  }}
                  onDelete={() => onDeleteChat(chat.id)}
                  onRename={(title) => onRenameChat(chat.id, title)}
                />
              ))}
            </>
          ) : (
            <PatientList
              onSelectPatient={(id) => {
                onSelectPatient(id);
                onClose();
              }}
              selectedPatientId={selectedPatientId}
            />
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-border">
          <p className="text-[10px] text-muted-foreground leading-relaxed">
            {activeTab === "chats"
              ? "Chats are synced to your server."
              : "Patient records persist across sessions."}
          </p>
        </div>
      </aside>
    </>
  );
}
