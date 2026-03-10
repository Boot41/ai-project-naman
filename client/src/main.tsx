import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import { alpha } from "@mui/material/styles";
import App from "./App";
import { AuthProvider } from "@/hooks/useAuth";
import "./styles/global.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});

const theme = createTheme({
  palette: {
    mode: "dark",
    primary: { main: "#2160f3", dark: "#1a4ec6", contrastText: "#f3f8ff" },
    background: { default: "#050d24", paper: "#09142f" },
    text: { primary: "#d7e8ff", secondary: "#7f98c3" },
    divider: alpha("#8ea9d9", 0.2),
  },
  shape: { borderRadius: 10 },
  typography: {
    fontFamily: '"Manrope", "Segoe UI", sans-serif',
    h4: { fontWeight: 700, letterSpacing: -0.25 },
    h6: { fontWeight: 700, letterSpacing: -0.15 },
    body2: { lineHeight: 1.6 },
  },
  components: {
    MuiTextField: {
      defaultProps: { fullWidth: true },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          transition: "all 180ms ease",
          backgroundColor: "rgba(12, 28, 59, 0.68)",
          color: "#bed4f8",
          "& .MuiOutlinedInput-notchedOutline": {
            borderColor: "#22355a",
          },
          "&:hover .MuiOutlinedInput-notchedOutline": {
            borderColor: "#2f4f82",
          },
          "&.Mui-focused .MuiOutlinedInput-notchedOutline": {
            borderWidth: 1.5,
            borderColor: "#3f73db",
          },
        },
      },
    },
    MuiButtonBase: {
      styleOverrides: {
        root: {
          "&.Mui-focusVisible": {
            outline: "2px solid #3f73db",
            outlineOffset: 2,
          },
        },
      },
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <AuthProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
