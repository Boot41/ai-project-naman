import {
  ButtonBase,
  Grid,
  Paper,
  Typography,
} from "@mui/material";

interface SuggestionCardsProps {
  suggestions: string[];
  onSelect: (value: string) => void;
}

export function SuggestionCards({ suggestions, onSelect }: SuggestionCardsProps) {
  return (
    <Grid container spacing={1.25} sx={{ mt: 1, width: "100%", maxWidth: 860 }}>
      {suggestions.map((suggestion) => (
        <Grid item xs={12} sm={6} key={suggestion}>
          <ButtonBase
            onClick={() => onSelect(suggestion)}
            sx={{ width: "100%", textAlign: "left", borderRadius: 2 }}
          >
            <Paper
              elevation={0}
              sx={{
                width: "100%",
                px: 1.75,
                py: 1.4,
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 2,
                transition: "all 170ms ease",
                "&:hover": {
                  borderColor: "primary.main",
                  bgcolor: "primary.50",
                },
              }}
            >
              <Typography variant="body2" color="text.primary">
                {suggestion}
              </Typography>
            </Paper>
          </ButtonBase>
        </Grid>
      ))}
    </Grid>
  );
}
