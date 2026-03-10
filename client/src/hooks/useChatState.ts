import { useMemo, useState } from "react";
import type { ChatMessage, ChatSession, SessionGroup } from "@/types/chat";

const starterSessions: ChatSession[] = [
  { id: "inc-992", title: "Payment Gateway Latency", lastUpdated: "10m ago" },
  { id: "inc-991", title: "DB Replica Lag", lastUpdated: "2h ago" },
  { id: "inc-986", title: "Auth Service 5xx Errors", lastUpdated: "Yesterday" },
  { id: "inc-978", title: "Memory Leak: Worker Nodes", lastUpdated: "3d ago" },
];

const filterSessions = (sessions: ChatSession[], query: string): SessionGroup[] => {
  const normalized = query.trim().toLowerCase();
  const filtered = normalized
    ? sessions.filter((session) => session.title.toLowerCase().includes(normalized))
    : sessions;

  return [{ label: "Recent Investigations", sessions: filtered }];
};

export interface ChatState {
  groupedSessions: SessionGroup[];
  selectedSession: ChatSession | null;
  sessionMessages: ChatMessage[];
  searchQuery: string;
  draft: string;
  isSending: boolean;
  setSearchQuery: (value: string) => void;
  setDraft: (value: string) => void;
  selectSession: (sessionId: string) => void;
  createNewChat: () => void;
  sendMessage: (content?: string) => Promise<void>;
}

export const useChatState = (): ChatState => {
  const [sessions, setSessions] = useState<ChatSession[]>(starterSessions);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string>(starterSessions[0]?.id ?? "");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [draft, setDraft] = useState<string>("");
  const [isSending, setIsSending] = useState<boolean>(false);

  const groupedSessions = useMemo(
    () => filterSessions(sessions, searchQuery),
    [sessions, searchQuery],
  );

  const selectedSession = useMemo(
    () => sessions.find((session) => session.id === selectedSessionId) ?? null,
    [sessions, selectedSessionId],
  );

  const sessionMessages = useMemo(
    () => messages.filter((message) => message.sessionId === selectedSessionId),
    [messages, selectedSessionId],
  );

  const selectSession = (sessionId: string) => {
    setSelectedSessionId(sessionId);
  };

  const createNewChat = () => {
    const id = `inc-${Date.now()}`;
    const newSession: ChatSession = {
      id,
      title: "New Investigation",
      lastUpdated: "now",
    };

    setSessions((prev) => [newSession, ...prev]);
    setSelectedSessionId(id);
    setDraft("");
  };

  const sendMessage = async (incoming?: string) => {
    const content = (incoming ?? draft).trim();
    if (!content || !selectedSessionId || isSending) {
      return;
    }

    setIsSending(true);

    const userMessage: ChatMessage = {
      id: `m-${Date.now()}-user`,
      sessionId: selectedSessionId,
      role: "user",
      content,
      createdAt: new Date().toISOString(),
    };

    // TODO: Replace with backend incident investigation API call.
    setMessages((prev) => [...prev, userMessage]);
    setSessions((prev) =>
      prev.map((session) =>
        session.id === selectedSessionId
          ? {
              ...session,
              title: session.title === "New Investigation" ? content.slice(0, 34) : session.title,
              lastUpdated: "now",
            }
          : session,
      ),
    );

    setDraft("");
    setIsSending(false);
  };

  return {
    groupedSessions,
    selectedSession,
    sessionMessages,
    searchQuery,
    draft,
    isSending,
    setSearchQuery,
    setDraft,
    selectSession,
    createNewChat,
    sendMessage,
  };
};
