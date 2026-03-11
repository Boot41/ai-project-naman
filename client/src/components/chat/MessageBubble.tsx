import { Paper, Stack, Typography } from "@mui/material";
import type { ChatMessage } from "@/types/chat";

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const structured = !isUser && message.structuredJson ? message.structuredJson : null;

  const status =
    structured && typeof structured.status === "string" ? structured.status : null;
  const hypotheses = Array.isArray(structured?.hypotheses) ? structured.hypotheses : [];
  const actions = Array.isArray(structured?.recommended_actions)
    ? structured.recommended_actions
    : [];
  const evidence = Array.isArray(structured?.evidence) ? structured.evidence : [];

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

        {structured ? (
          <Stack spacing={1.2} sx={{ mt: 1.4 }}>
            {status ? (
              <Typography variant="caption" sx={{ color: "#8fb4f0" }}>
                Status: {status}
              </Typography>
            ) : null}

            {hypotheses.length > 0 ? (
              <Stack spacing={0.35}>
                <Typography variant="caption" sx={{ color: "#9fc0f7", fontWeight: 700 }}>
                  Hypotheses
                </Typography>
                {hypotheses.slice(0, 3).map((item, idx) => {
                  const cause =
                    item && typeof item === "object" && "cause" in item
                      ? String(item.cause ?? "")
                      : "";
                  if (!cause) {
                    return null;
                  }
                  return (
                    <Typography key={`hyp-${idx}`} variant="caption" sx={{ color: "#cfe2ff" }}>
                      {idx + 1}. {cause}
                    </Typography>
                  );
                })}
              </Stack>
            ) : null}

            {actions.length > 0 ? (
              <Stack spacing={0.35}>
                <Typography variant="caption" sx={{ color: "#9fc0f7", fontWeight: 700 }}>
                  Recommended Actions
                </Typography>
                {actions.slice(0, 5).map((item, idx) => (
                  <Typography key={`act-${idx}`} variant="caption" sx={{ color: "#cfe2ff" }}>
                    {idx + 1}. {String(item)}
                  </Typography>
                ))}
              </Stack>
            ) : null}

            {evidence.length > 0 ? (
              <Stack spacing={0.35}>
                <Typography variant="caption" sx={{ color: "#9fc0f7", fontWeight: 700 }}>
                  Evidence
                </Typography>
                {evidence.slice(0, 4).map((item, idx) => {
                  const snippet =
                    item && typeof item === "object" && "snippet" in item
                      ? String(item.snippet ?? "")
                      : "";
                  if (!snippet) {
                    return null;
                  }
                  return (
                    <Typography key={`ev-${idx}`} variant="caption" sx={{ color: "#cfe2ff" }}>
                      {idx + 1}. {snippet}
                    </Typography>
                  );
                })}
              </Stack>
            ) : null}
          </Stack>
        ) : null}
      </Paper>
    </Stack>
  );
}
