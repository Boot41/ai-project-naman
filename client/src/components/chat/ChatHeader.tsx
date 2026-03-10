import AutoAwesomeRoundedIcon from "@mui/icons-material/AutoAwesomeRounded";
import { Button, Stack, Typography } from "@mui/material";

interface ChatHeaderProps {
  title: string;
  onLogout: () => void;
}

export function ChatHeader({ title, onLogout }: ChatHeaderProps) {
  return (
    <Stack
      component="header"
      direction="row"
      alignItems={{ xs: "flex-start", md: "center" }}
      justifyContent="space-between"
      spacing={2}
      sx={{
        px: { xs: 2, md: 3 },
        py: 1.5,
        borderBottom: "1px solid #1c2b46",
        bgcolor: "#09142f",
        flexWrap: { xs: "wrap", md: "nowrap" },
        rowGap: 1.2,
      }}
    >
      <Stack minWidth={0} spacing={0.3} sx={{ flex: 1, width: { xs: "100%", md: "auto" } }}>
        <Stack direction="row" spacing={1} alignItems="center" minWidth={0}>
          <AutoAwesomeRoundedIcon sx={{ color: "#4e83fa", fontSize: 18 }} />
          <Typography sx={{ color: "#d9e8ff", fontWeight: 700, fontSize: { xs: 25 / 2, md: 39 / 2 } }} noWrap>
            Active Incident: {title}
          </Typography>
        </Stack>
        <Typography variant="caption" sx={{ color: "#7091c5" }}>
          Analyzing postgres logs and runbooks • 14:15 UTC
        </Typography>
      </Stack>

      <Stack
        direction="row"
        spacing={1}
        sx={{ width: { xs: "100%", md: "auto" }, justifyContent: { xs: "flex-end", md: "flex-start" } }}
      >
        <Button
          size="small"
          variant="outlined"
          sx={{
            borderColor: "#2a3f66",
            color: "#a6bfeb",
            textTransform: "none",
            fontWeight: 700,
            borderRadius: 1.5,
            "&:hover": { borderColor: "#3a5a91", bgcolor: "rgba(52, 77, 124, 0.25)" },
          }}
        >
          Export JSON
        </Button>
        <Button
          size="small"
          variant="contained"
          sx={{
            bgcolor: "#2160f3",
            textTransform: "none",
            fontWeight: 700,
            borderRadius: 1.5,
            boxShadow: "none",
            "&:hover": { bgcolor: "#1e56d8" },
          }}
        >
          Resolve Incident
        </Button>
        <Button
          size="small"
          variant="outlined"
          onClick={onLogout}
          sx={{
            borderColor: "#2a3f66",
            color: "#a6bfeb",
            textTransform: "none",
            fontWeight: 700,
            borderRadius: 1.5,
            "&:hover": { borderColor: "#3a5a91", bgcolor: "rgba(52, 77, 124, 0.25)" },
          }}
        >
          Logout
        </Button>
      </Stack>
    </Stack>
  );
}
