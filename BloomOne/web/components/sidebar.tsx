"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import type { ChatSession } from "@/lib/use-chats";

interface SidebarProps {
  chats: ChatSession[];
  activeChatId: string | null;
  onSelectChat: (id: string) => void;
  onNewChat: () => void;
  onDeleteChat: (id: string) => void;
  onRenameChat: (id: string, title: string) => void;
  isOpen: boolean;
  onClose: () => void;
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
        className={`w-full px-3 py-2.5 rounded-lg text-sm bg-[var(--secondary)]`}
      >
        <input
          ref={inputRef}
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onBlur={commitRename}
          onKeyDown={handleKeyDown}
          className="w-full bg-transparent text-[var(--foreground)] outline-none 
                   border-b border-[var(--primary)] pb-0.5 text-sm"
          maxLength={80}
        />
        <span className="text-[10px] text-[var(--muted-foreground)] mt-1 block">
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
            ? "bg-[var(--secondary)] text-[var(--foreground)]"
            : "text-[var(--muted-foreground)] hover:bg-[var(--secondary)]/50 hover:text-[var(--foreground)]"
        }`}
    >
      <div className="flex items-start justify-between gap-1">
        <span className="truncate leading-snug flex-1">{chat.title}</span>
        <div className="flex-shrink-0 flex items-center gap-0.5 opacity-0 group-hover:opacity-60">
          {/* Rename button */}
          <button
            onClick={(e) => {
              e.stopPropagation();
              setEditValue(chat.title);
              setEditing(true);
            }}
            className="hover:!opacity-100 transition-opacity p-0.5 rounded hover:bg-[var(--primary)]/20"
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
            className="hover:!opacity-100 transition-opacity p-0.5 rounded hover:bg-[var(--destructive)]/20"
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
      <span className="text-[10px] text-[var(--muted-foreground)] mt-0.5 block">
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
}: SidebarProps) {
  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={`fixed lg:static inset-y-0 left-0 z-50 w-72 
                   bg-[var(--card)] border-r border-[var(--border)]
                   flex flex-col transition-transform duration-300 ease-in-out
                   ${isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
          <div className="flex items-center gap-2">
            <span className="text-lg">🧬</span>
            <span className="text-sm font-semibold text-[var(--foreground)]">
              BloomOne
            </span>
          </div>
          <button
            onClick={onNewChat}
            className="p-1.5 rounded-lg hover:bg-[var(--secondary)] transition-colors"
            title="New chat"
          >
            <svg
              className="w-4 h-4 text-[var(--foreground)]"
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
        </div>

        {/* Chat list */}
        <div className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5">
          {chats.length === 0 && (
            <p className="text-xs text-[var(--muted-foreground)] text-center py-8 px-4">
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
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-[var(--border)]">
          <p className="text-[10px] text-[var(--muted-foreground)] leading-relaxed">
            Chats are synced to your server.
          </p>
        </div>
      </aside>
    </>
  );
}
