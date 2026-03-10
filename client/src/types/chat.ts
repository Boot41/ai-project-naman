export type MessageRole = "user" | "assistant" | "system";

export interface ChatSession {
  id: string;
  title: string;
  sessionType: "chat";
  status: "active" | "closed";
  lastActivityAt: string;
  createdAt: string;
  messageCount: number;
}

export interface ChatMessage {
  id: string;
  sessionId: string;
  role: MessageRole;
  content: string;
  structuredJson?: Record<string, unknown> | null;
  createdAt: string;
}

export interface SessionGroup {
  label: string;
  sessions: ChatSession[];
}
