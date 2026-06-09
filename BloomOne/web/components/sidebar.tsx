"use client";

import type { ChatSession } from "@/lib/use-chats";

interface SidebarProps {
  chats: ChatSession[];
  activeChatId: string | null;
  onSelectChat: (id: string) => void;
  onNewChat: () => void;
  onDeleteChat: (id: string) => void;
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

export function Sidebar({
  chats,
  activeChatId,
  onSelectChat,
  onNewChat,
  onDeleteChat,
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
            <button
              key={chat.id}
              onClick={() => {
                onSelectChat(chat.id);
                onClose();
              }}
              className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all duration-150 group
                ${
                  chat.id === activeChatId
                    ? "bg-[var(--secondary)] text-[var(--foreground)]"
                    : "text-[var(--muted-foreground)] hover:bg-[var(--secondary)]/50 hover:text-[var(--foreground)]"
                }`}
            >
              <div className="flex items-start justify-between gap-2">
                <span className="truncate leading-snug flex-1">
                  {chat.title}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteChat(chat.id);
                  }}
                  className="flex-shrink-0 opacity-0 group-hover:opacity-60 hover:!opacity-100 
                           transition-opacity p-0.5 rounded hover:bg-[var(--destructive)]/20"
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
              <span className="text-[10px] text-[var(--muted-foreground)] mt-0.5 block">
                {formatTime(chat.updatedAt)}
              </span>
            </button>
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
