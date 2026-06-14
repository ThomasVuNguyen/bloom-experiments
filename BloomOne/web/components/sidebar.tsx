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
  isCollapsed: boolean;
  onToggleCollapse: () => void;
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
            className="text-[10px] text-muted-foreground hover:text-primary transition-colors px-1 py-0.5 rounded hover:bg-primary/10"
            title="Rename chat"
          >
            Edit
          </button>
          {/* Delete button */}
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="text-[10px] text-muted-foreground hover:text-destructive transition-colors px-1 py-0.5 rounded hover:bg-destructive/10"
            title="Delete chat"
          >
            Del
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
  isCollapsed,
  onToggleCollapse,
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
        className={`fixed lg:static inset-y-0 left-0 z-50
                   bg-card border-r border-border
                   flex flex-col transition-all duration-300 ease-in-out
                   ${isCollapsed ? "w-0 lg:w-12 overflow-hidden" : "w-72"}
                   ${isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}
      >
        {/* Collapsed state — just a thin expand bar on desktop */}
        {isCollapsed && (
          <div className="hidden lg:flex flex-col items-center py-3 w-12">
            <button
              onClick={onToggleCollapse}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors px-1 py-2 rounded"
              title="Expand sidebar"
            >
              »
            </button>
          </div>
        )}

        {/* Full sidebar content — hidden when collapsed */}
        {!isCollapsed && (
          <>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <div>
            <span className="text-sm font-serif font-semibold text-foreground">
              BloomOne
            </span>
            <p className="text-[10px] text-muted-foreground">
              Neoantigen Vaccine Design
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            {activeTab === "chats" && (
              <button
                onClick={onNewChat}
                className="px-2 py-1 rounded-lg border border-primary text-primary text-xs font-medium
                           hover:bg-primary hover:text-primary-foreground transition-colors"
                title="New chat"
              >
                + New
              </button>
            )}
            <button
              onClick={onToggleCollapse}
              className="hidden lg:inline-flex text-xs text-muted-foreground hover:text-foreground transition-colors px-1.5 py-1 rounded hover:bg-secondary"
              title="Collapse sidebar"
            >
              «
            </button>
          </div>
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
            Chats
          </button>
          <button
            onClick={() => setActiveTab("patients")}
            className={`flex-1 px-3 py-2 text-xs font-medium transition-colors flex items-center justify-center gap-1.5
              ${activeTab === "patients"
                ? "text-primary border-b-2 border-primary"
                : "text-muted-foreground hover:text-foreground"}`}
          >
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
          </>
        )}
      </aside>
    </>
  );
}
