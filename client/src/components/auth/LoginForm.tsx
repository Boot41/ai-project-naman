import {
  Alert,
  Box,
  Button,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useMemo, useState, type FormEvent } from "react";

interface LoginFormProps {
  onSubmit: (payload: { email: string; password: string }) => Promise<string | null>;
}

const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function LoginForm({ onSubmit }: LoginFormProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [touched, setTouched] = useState<{ email: boolean; password: boolean }>({
    email: false,
    password: false,
  });

  const emailError = useMemo(() => {
    if (!touched.email) {
      return "";
    }
    if (!email.trim()) {
      return "Email is required";
    }
    if (!emailRegex.test(email.trim())) {
      return "Enter a valid email address";
    }
    return "";
  }, [email, touched.email]);

  const passwordError = useMemo(() => {
    if (!touched.password) {
      return "";
    }
    if (!password.trim()) {
      return "Password is required";
    }
    if (password.length < 6) {
      return "Password must be at least 6 characters";
    }
    return "";
  }, [password, touched.password]);

  const isValid = Boolean(!emailError && !passwordError && email.trim() && password.trim());

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setTouched({ email: true, password: true });
    setError(null);

    if (!isValid) {
      return;
    }

    setIsSubmitting(true);
    const message = await onSubmit({ email: email.trim(), password });
    if (message) {
      setError(message);
    }
    setIsSubmitting(false);
  };

  return (
    <Box
      component="form"
      onSubmit={handleSubmit}
      noValidate
      sx={{ width: "100%" }}
      aria-label="Login form"
    >
      <Stack spacing={2}>
        <Stack spacing={0.75}>
          <Typography variant="h4" sx={{ fontSize: 28, color: "#d9e8ff" }}>
            Sign in to OpsCopilot
          </Typography>
          <Typography variant="body2" sx={{ color: "#8ca7d4" }}>
            AI-assisted operations workspace for incident triage, system diagnostics, and runbook support.
          </Typography>
        </Stack>

        {error && (
          <Alert
            severity="error"
            sx={{
              bgcolor: "rgba(127, 29, 29, 0.22)",
              color: "#fecaca",
              border: "1px solid rgba(248, 113, 113, 0.35)",
            }}
          >
            {error}
          </Alert>
        )}

        <TextField
          label="Email"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          onBlur={() => setTouched((prev) => ({ ...prev, email: true }))}
          error={Boolean(emailError)}
          helperText={emailError || " "}
          autoComplete="email"
          required
          fullWidth
        />

        <TextField
          label="Password"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          onBlur={() => setTouched((prev) => ({ ...prev, password: true }))}
          error={Boolean(passwordError)}
          helperText={passwordError || " "}
          autoComplete="current-password"
          required
          fullWidth
        />

        <Button
          type="submit"
          variant="contained"
          size="large"
          disabled={!isValid || isSubmitting}
          sx={{
            mt: 0.2,
            bgcolor: "#2160f3",
            color: "#deebff",
            textTransform: "none",
            fontWeight: 700,
            boxShadow: "none",
            borderRadius: 2,
            "&:hover": { bgcolor: "#1e56d8" },
          }}
        >
          {isSubmitting ? "Signing in..." : "Sign in"}
        </Button>

        <Typography variant="caption" sx={{ color: "#7f98c3" }}>
          Use your OpsCopilot account credentials.
        </Typography>
      </Stack>
    </Box>
  );
}
