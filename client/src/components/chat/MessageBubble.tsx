import { Paper, Stack, Typography } from "@mui/material";
import type { ChatMessage } from "@/types/chat";

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <Stack alignItems={isUser ? "flex-end" : "flex-start"} sx={{ width: "100%" }}>
      <Paper
        elevation={0}
        sx={{
          maxWidth: { xs: "92%", md: "68%" },
          px: 2,
          py: 1.5,
          borderRadius: 2.2,
          bgcolor: isUser ? "#2160f3" : "#112449",
          color: isUser ? "#ecf4ff" : "#d7e8ff",
          border: "1px solid",
          borderColor: isUser ? "#3d73e7" : "#29406a",
        }}
      >
        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", lineHeight: 1.65 }}>
          {message.content}
        </Typography>
      </Paper>
    </Stack>
  );
}
