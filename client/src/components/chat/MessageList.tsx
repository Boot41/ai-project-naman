import { Box, Button, Stack, Typography } from "@mui/material";
import { MessageBubble } from "@/components/chat/MessageBubble";
import type { ChatMessage } from "@/types/chat";

interface MessageListProps {
  messages: ChatMessage[];
}

export function MessageList({ messages }: MessageListProps) {
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
        <Button
          variant="outlined"
          size="small"
          sx={{ borderColor: "#4a5e87", color: "#95aed8", textTransform: "none" }}
        >
          Preview
        </Button>
      </Stack>
    );
  }

  return (
    <Stack spacing={2} sx={{ px: { xs: 2, md: 4 }, py: 2.5 }}>
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}
      <Box sx={{ height: 4 }} />
    </Stack>
  );
}
