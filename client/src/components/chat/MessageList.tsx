import { Box, Stack, Typography } from "@mui/material";
import { MessageBubble } from "@/components/chat/MessageBubble";
import type { ChatMessage } from "@/types/chat";

interface MessageListProps {
  messages: ChatMessage[];
  isThinking?: boolean;
}

export function MessageList({ messages, isThinking = false }: MessageListProps) {
  if (messages.length === 0) {
    return (
      <Stack
        alignItems="center"
        justifyContent="center"
        sx={{ height: "100%", px: 2 }}
        spacing={1.1}
      >
        <Typography variant="h6" sx={{ color: "#8ea8d4", textAlign: "center" }}>
          Start an investigation query to analyze logs, incidents, and runbooks.
        </Typography>
      </Stack>
    );
  }

  return (
    <Stack spacing={0} sx={{ px: { xs: 2, md: 4 }, py: 2.5 }}>
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}
      {isThinking ? (
        <Typography
          variant="caption"
          sx={{
            color: "#9fc0f7",
            bgcolor: "#112449",
            border: "1px solid #29406a",
            borderRadius: 2.2,
            px: 2,
            py: 1.2,
            maxWidth: 700,
            mb: 2.25,
          }}
        >
          Thinking...
        </Typography>
      ) : null}
      <Box sx={{ height: 4 }} />
    </Stack>
  );
}
