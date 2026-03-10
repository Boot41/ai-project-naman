import { useCallback, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import type { ChatMessage, ChatSession, SessionGroup } from "@/types/chat";

interface SessionApi {
  id: string;
  user_id: number;
  incident_id: number | null;
  session_type: "chat";
  title: string | null;
  status: "active" | "closed";
  created_at: string;
  last_activity_at: string;
  message_count?: number;
}

interface MessageApi {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system";
  content_text: string;
  structured_json?: Record<string, unknown> | null;
  created_at: string;
}

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
  deleteSession: (sessionId: string) => Promise<void>;
  sendMessage: (content?: string) => Promise<void>;
}

const mapSession = (raw: SessionApi): ChatSession => ({
  id: raw.id,
  title: raw.title ?? "New Investigation",
  sessionType: raw.session_type,
  status: raw.status,
  lastActivityAt: raw.last_activity_at,
  createdAt: raw.created_at,
  messageCount: raw.message_count ?? 0,
});

const mapMessage = (raw: MessageApi): ChatMessage => ({
  id: raw.id,
  sessionId: raw.session_id,
  role: raw.role,
  content: raw.content_text,
  structuredJson: raw.structured_json ?? null,
  createdAt: raw.created_at,
});

export const useChatState = (): ChatState => {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string>("");
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

  const fetchMessages = useCallback(async (sessionId: string) => {
    const response = await api.get<{ messages: MessageApi[] }>(`/api/v1/chat/sessions/${sessionId}/messages`);
    setMessages(response.data.messages.map(mapMessage));
  }, []);

  const fetchSessions = useCallback(async () => {
    const response = await api.get<{ sessions: SessionApi[] }>("/api/v1/chat/sessions");
    const nextSessions = response.data.sessions.map(mapSession);
    setSessions(nextSessions);
    if (!selectedSessionId && nextSessions.length > 0) {
      setSelectedSessionId(nextSessions[0].id);
    } else if (selectedSessionId && !nextSessions.some((s) => s.id === selectedSessionId)) {
      setSelectedSessionId(nextSessions[0]?.id ?? "");
    }
  }, [selectedSessionId]);

  useEffect(() => {
    void fetchSessions();
  }, [fetchSessions]);

  useEffect(() => {
    if (!selectedSessionId) {
      setMessages([]);
      return;
    }
    void fetchMessages(selectedSessionId);
  }, [fetchMessages, selectedSessionId]);

  const createNewChat = () => {
    void (async () => {
      const response = await api.post<SessionApi>("/api/v1/chat/sessions", {});
      const newSession = mapSession(response.data);
      setSessions((prev) => [newSession, ...prev]);
      setSelectedSessionId(newSession.id);
      setMessages([]);
      setDraft("");
    })();
  };

  const deleteSession = async (sessionId: string) => {
    await api.delete(`/api/v1/chat/sessions/${sessionId}`);
    setSessions((prev) => {
      const remaining = prev.filter((s) => s.id !== sessionId);
      if (selectedSessionId === sessionId) {
        const nextId = remaining[0]?.id ?? "";
        setSelectedSessionId(nextId);
        if (!nextId) setMessages([]);
      }
      return remaining;
    });
  };

  const sendMessage = async (incoming?: string) => {
    const content = (incoming ?? draft).trim();
    if (!content || !selectedSessionId || isSending) {
      return;
    }
    setIsSending(true);
    try {
      const response = await api.post<{
        user_message: MessageApi;
        assistant_message: MessageApi;
      }>(`/api/v1/chat/sessions/${selectedSessionId}/messages`, {
        content_text: content,
      });

      const userMessage = mapMessage(response.data.user_message);
      const assistantMessage = mapMessage(response.data.assistant_message);
      setMessages((prev) => [...prev, userMessage, assistantMessage]);
      await fetchSessions();
      setDraft("");
    } finally {
      setIsSending(false);
    }
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
    deleteSession,
    sendMessage,
  };
};
