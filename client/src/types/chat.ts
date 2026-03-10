export type MessageRole = "user" | "assistant";

export interface ChatSession {
  id: string;
  title: string;
  lastUpdated: string;
}

export interface ChatMessage {
  id: string;
  sessionId: string;
  role: MessageRole;
  content: string;
  createdAt: string;
}

export interface SessionGroup {
  label: string;
  sessions: ChatSession[];
}
