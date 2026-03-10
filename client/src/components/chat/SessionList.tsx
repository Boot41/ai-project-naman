import { Stack, Typography } from "@mui/material";
import { SessionItem } from "@/components/chat/SessionItem";
import type { SessionGroup } from "@/types/chat";

interface SessionListProps {
  groups: SessionGroup[];
  activeSessionId: string | null;
  onSelect: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
}

export function SessionList({ groups, activeSessionId, onSelect, onDelete }: SessionListProps) {
  return (
    <Stack spacing={2}>
      {groups.map((group) => (
        <Stack spacing={1} key={group.label}>
          <Typography
            variant="overline"
            sx={{ color: "#5e78a5", letterSpacing: 0.8, fontSize: 12, fontWeight: 700, px: 0.5 }}
          >
            {group.label}
          </Typography>
          <Stack spacing={0.65}>
            {group.sessions.length === 0 ? (
              <Typography variant="body2" sx={{ color: "#6781b0", px: 0.5 }}>
                No investigations found.
              </Typography>
            ) : (
              group.sessions.map((session) => (
                <SessionItem
                  key={session.id}
                  session={session}
                  isActive={activeSessionId === session.id}
                  onClick={onSelect}
                  onDelete={onDelete}
                />
              ))
            )}
          </Stack>
        </Stack>
      ))}
    </Stack>
  );
}
