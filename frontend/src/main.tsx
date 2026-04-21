import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { PortfolioProvider } from "./state/portfolioContext";
import "./index.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Missing #root element in index.html");
}

// Shared QueryClient for the whole app. staleTime keeps optimization results
// warm for 30 s so switching tabs doesn't thrash the backend; retry is set to
// 1 at the client level and overridden per-query for non-retriable errors
// (see `lib/queries.ts`).
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <PortfolioProvider>
        <App />
      </PortfolioProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
