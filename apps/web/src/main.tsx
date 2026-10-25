import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./app/App";
import Boot from "./app/Boot";
import "./styles/tokens.css";
import "./styles/global.css";

const queryClient = new QueryClient();

async function start() {
  if (import.meta.env.DEV && import.meta.env.VITE_USE_MOCK === "true") {
    const { worker } = await import("./mocks/browser");
    await worker.start({ onUnhandledRequest: "bypass" });
  }
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Boot>
            <App />
          </Boot>
        </BrowserRouter>
      </QueryClientProvider>
    </React.StrictMode>,
  );
}

void start();
