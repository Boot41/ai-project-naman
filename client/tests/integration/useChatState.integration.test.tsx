import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import api from "@/lib/api";
import { useChatState } from "@/hooks/useChatState";

interface SessionRecord {
  id: string;
  user_id: number;
  incident_id: number | null;
  session_type: "chat";
  title: string | null;
  status: "active" | "closed";
  created_at: string;
  last_activity_at: string;
  message_count: number;
}

interface MessageRecord {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system";
  content_text: string;
  structured_json: Record<string, unknown> | null;
  created_at: string;
}

describe("useChatState integration", () => {
  let sessions: SessionRecord[];
  let messagesBySession: Record<string, MessageRecord[]>;

  beforeEach(() => {
    sessions = [
      {
        id: "s-1",
        user_id: 1,
        incident_id: null,
        session_type: "chat",
        title: "First Session",
        status: "active",
        created_at: new Date().toISOString(),
        last_activity_at: new Date().toISOString(),
        message_count: 0,
      },
    ];
    messagesBySession = { "s-1": [] };

    vi.spyOn(api, "get").mockImplementation(async (url: string) => {
      if (url === "/api/v1/chat/sessions") {
        return { data: { sessions } };
      }
      if (url.includes("/messages")) {
        const sessionId = url.split("/")[5];
        return { data: { messages: messagesBySession[sessionId] ?? [] } };
      }
      throw new Error(`Unhandled GET ${url}`);
    });

    vi.spyOn(api, "post").mockImplementation(async (url: string, body?: unknown) => {
      if (url === "/api/v1/chat/sessions") {
        const created: SessionRecord = {
          id: "s-2",
          user_id: 1,
          incident_id: null,
          session_type: "chat",
          title: "New Investigation",
          status: "active",
          created_at: new Date().toISOString(),
          last_activity_at: new Date().toISOString(),
          message_count: 0,
        };
        sessions = [created, ...sessions];
        messagesBySession["s-2"] = [];
        return { data: created };
      }

      if (url.includes("/messages")) {
        const sessionId = url.split("/")[5];
        const content = (body as { content_text: string }).content_text;
        const userMessage: MessageRecord = {
          id: "m-user-1",
          session_id: sessionId,
          role: "user",
          content_text: content,
          structured_json: null,
          created_at: new Date().toISOString(),
        };
        const assistantMessage: MessageRecord = {
          id: "m-ai-1",
          session_id: sessionId,
          role: "assistant",
          content_text: "assistant reply",
          structured_json: { summary: "assistant reply" },
          created_at: new Date().toISOString(),
        };
        messagesBySession[sessionId] = [userMessage, assistantMessage];
        sessions = sessions.map((s) =>
          s.id === sessionId
            ? { ...s, title: content.slice(0, 48), message_count: 2, last_activity_at: new Date().toISOString() }
            : s,
        );
        return { data: { user_message: userMessage, assistant_message: assistantMessage } };
      }
      throw new Error(`Unhandled POST ${url}`);
    });

    vi.spyOn(api, "delete").mockImplementation(async (url: string) => {
      const sessionId = url.split("/").at(-1) as string;
      sessions = sessions.filter((s) => s.id !== sessionId);
      delete messagesBySession[sessionId];
      return { data: null };
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads sessions, creates, sends, and deletes chat session", async () => {
    const { result } = renderHook(() => useChatState());

    await waitFor(() => expect(result.current.groupedSessions[0]?.sessions.length).toBe(1));
    expect(result.current.selectedSession?.id).toBe("s-1");

    act(() => {
      result.current.createNewChat();
    });
    await waitFor(() => expect(result.current.selectedSession?.id).toBe("s-2"));

    await act(async () => {
      await result.current.sendMessage("latency in checkout service");
    });
    await waitFor(() => expect(result.current.sessionMessages.length).toBe(2));
    expect(result.current.sessionMessages[0].role).toBe("user");
    expect(result.current.sessionMessages[1].role).toBe("assistant");

    await act(async () => {
      await result.current.deleteSession("s-2");
    });
    await waitFor(() => expect(result.current.selectedSession?.id).toBe("s-1"));
  });
});
