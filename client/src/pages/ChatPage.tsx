import MenuRoundedIcon from "@mui/icons-material/MenuRounded";
import {
  Box,
  Drawer,
  IconButton,
  Stack,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import { ChatHeader } from "@/components/chat/ChatHeader";
import { Composer } from "@/components/chat/Composer";
import { MessageList } from "@/components/chat/MessageList";
import { Sidebar } from "@/components/chat/Sidebar";
import { useAuth } from "@/hooks/useAuth";
import { useChatState } from "@/hooks/useChatState";
import { useEffect, useRef, useState } from "react";

export function ChatPage() {
  const {
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
  } = useChatState();
  const { logout } = useAuth();

  const [mobileOpen, setMobileOpen] = useState(false);
  const theme = useTheme();
  const isDesktop = useMediaQuery(theme.breakpoints.up("lg"));
  const messagesContainerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = messagesContainerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [sessionMessages]);

  useEffect(() => {
    if (isDesktop) {
      setMobileOpen(false);
    }
  }, [isDesktop]);

  const sidebar = (
    <Sidebar
      groups={groupedSessions}
      activeSessionId={selectedSession?.id ?? null}
      searchQuery={searchQuery}
      onSearchQueryChange={setSearchQuery}
      onSelectSession={(sessionId) => {
        selectSession(sessionId);
        setMobileOpen(false);
      }}
      onDeleteSession={(sessionId) => {
        void deleteSession(sessionId);
      }}
      onNewChat={() => {
        createNewChat();
        setMobileOpen(false);
      }}
    />
  );

  return (
    <Stack sx={{ minHeight: "100vh", bgcolor: "#050d24" }} direction="row">
      {isDesktop ? (
        sidebar
      ) : (
        <Drawer open={mobileOpen} onClose={() => setMobileOpen(false)}>
          {sidebar}
        </Drawer>
      )}

      <Stack sx={{ flex: 1, minWidth: 0 }} component="main">
        <Stack
          direction="row"
          alignItems="center"
          sx={{
            borderBottom: "1px solid #1b2b48",
            bgcolor: "#09142f",
            px: 1,
            py: 0.7,
            display: { lg: "none" },
          }}
        >
          <IconButton aria-label="Open chat sessions" onClick={() => setMobileOpen(true)}>
            <MenuRoundedIcon sx={{ color: "#9fb8e2" }} fontSize="small" />
          </IconButton>
        </Stack>

        <ChatHeader
          title={selectedSession?.title ?? "No Active Investigation"}
          onLogout={logout}
        />

        <Box ref={messagesContainerRef} sx={{ flex: 1, overflowY: "auto" }}>
          <MessageList messages={sessionMessages} />
        </Box>

        <Composer value={draft} isSending={isSending} onChange={setDraft} onSend={() => sendMessage()} />
      </Stack>
    </Stack>
  );
}
