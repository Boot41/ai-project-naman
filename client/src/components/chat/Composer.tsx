import AttachFileRoundedIcon from "@mui/icons-material/AttachFileRounded";
import MicNoneRoundedIcon from "@mui/icons-material/MicNoneRounded";
import SendRoundedIcon from "@mui/icons-material/SendRounded";
import {
  IconButton,
  Paper,
  Stack,
  TextField,
} from "@mui/material";
import { useEffect, useRef } from "react";

interface ComposerProps {
  value: string;
  isSending: boolean;
  onChange: (value: string) => void;
  onSend: () => void;
}

export function Composer({ value, isSending, onChange, onSend }: ComposerProps) {
  const textAreaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const textarea = textAreaRef.current;
    if (!textarea) {
      return;
    }
    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 220)}px`;
  }, [value]);

  return (
    <Stack sx={{ px: { xs: 1.2, md: 0 }, pb: { xs: 1.2, md: 1.8 }, bgcolor: "#050d24" }}>
      <Paper
        elevation={0}
        sx={{
          width: { xs: "100%", md: "70%" },
          mx: "auto",
          border: "1px solid #2b3f66",
          borderRadius: 2.2,
          bgcolor: "#101e3b",
          px: 1,
          py: 0.7,
          boxShadow: "0 8px 20px rgba(3, 10, 28, 0.35)",
        }}
      >
        <Stack direction="row" spacing={0.5} alignItems="flex-end">
          <IconButton aria-label="Attach file" size="small" sx={{ color: "#89a3cf" }}>
            <AttachFileRoundedIcon fontSize="small" />
          </IconButton>

          <TextField
            multiline
            fullWidth
            maxRows={8}
            minRows={1}
            inputRef={textAreaRef}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder="Ask OpsCopilot to query logs, check runbooks, or summarize an incident..."
            aria-label="Message input"
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                onSend();
              }
            }}
            disabled={isSending}
            sx={{
              "& .MuiOutlinedInput-root": {
                color: "#aecdff",
                bgcolor: "transparent",
                borderRadius: 1.5,
                "& fieldset": { borderColor: "transparent" },
                "&:hover fieldset": { borderColor: "transparent" },
                "&.Mui-focused fieldset": { borderColor: "transparent" },
              },
            }}
          />

          <IconButton aria-label="Voice input" size="small" sx={{ color: "#89a3cf" }}>
            <MicNoneRoundedIcon fontSize="small" />
          </IconButton>

          <IconButton
            aria-label="Send message"
            size="small"
            onClick={onSend}
            disabled={isSending || value.trim().length === 0}
            sx={{
              bgcolor: "rgba(255, 255, 255, 0.1)",
              color: "#a7bde6",
              width: 30,
              height: 30,
              "&:hover": { bgcolor: "rgba(255, 255, 255, 0.16)" },
            }}
          >
            <SendRoundedIcon sx={{ fontSize: 16 }} />
          </IconButton>
        </Stack>
      </Paper>

      <TypographyFooter />
    </Stack>
  );
}

function TypographyFooter() {
  return (
    <p
      style={{
        color: "#4f6792",
        textAlign: "center",
        margin: "10px 0 0",
        fontSize: "11px",
      }}
    >
      OpsCopilot can make mistakes. Verify critical actions in Postgres and review runbooks manually.
    </p>
  );
}
