import ChatBubbleOutlineRoundedIcon from "@mui/icons-material/ChatBubbleOutlineRounded";
import { ButtonBase, Stack, Typography } from "@mui/material";
import type { ChatSession } from "@/types/chat";

interface SessionItemProps {
  session: ChatSession;
  isActive: boolean;
  onClick: (sessionId: string) => void;
}

export function SessionItem({ session, isActive, onClick }: SessionItemProps) {
  return (
    <ButtonBase
      onClick={() => onClick(session.id)}
      sx={{
        width: "100%",
        py: 1,
        px: 1.2,
        borderRadius: 1.6,
        textAlign: "left",
        alignItems: "flex-start",
        justifyContent: "flex-start",
        border: "1px solid",
        borderColor: isActive ? "rgba(56, 122, 255, 0.38)" : "transparent",
        bgcolor: isActive ? "rgba(33, 90, 219, 0.26)" : "transparent",
        transition: "all 160ms ease",
        "&:hover": {
          bgcolor: "rgba(33, 90, 219, 0.22)",
          borderColor: "rgba(56, 122, 255, 0.34)",
        },
      }}
    >
      <Stack direction="row" spacing={1.2} width="100%">
        <ChatBubbleOutlineRoundedIcon sx={{ color: "#8ca7d4", fontSize: 18, mt: 0.2 }} />
        <Stack spacing={0.2} minWidth={0}>
          <Typography variant="body2" sx={{ color: "#c7d6f2", fontWeight: 600 }} noWrap>
            {session.title}
          </Typography>
          <Typography variant="caption" sx={{ color: "#6781b0" }}>
            {session.lastUpdated}
          </Typography>
        </Stack>
      </Stack>
    </ButtonBase>
  );
}
