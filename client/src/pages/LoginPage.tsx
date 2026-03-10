import { Box, Container, Paper } from "@mui/material";
import { LoginForm } from "@/components/auth/LoginForm";
import { useAuth } from "@/hooks/useAuth";
import { useNavigate } from "react-router-dom";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();

  return (
    <Box
      component="main"
      sx={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        bgcolor: "#050d24",
        px: 2,
      }}
    >
      <Container maxWidth="sm">
        <Paper
          elevation={0}
          sx={{
            p: { xs: 2.5, sm: 3.5 },
            borderRadius: 3,
            border: "1px solid #1d2a45",
            bgcolor: "#09142f",
            boxShadow: "0 16px 40px rgba(3, 10, 28, 0.4)",
          }}
        >
          <LoginForm
            onSubmit={async (payload) => {
              const result = await login(payload);
              if (result.ok) {
                navigate("/app", { replace: true });
                return null;
              }
              return result.message ?? "Unable to sign in";
            }}
          />
        </Paper>
      </Container>
    </Box>
  );
}
