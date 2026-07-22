import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { I18nProvider } from "./i18n";
import { useWorkspace } from "./hooks/useWorkspace";
import "./styles.css";

const queryClient = new QueryClient();

/**
 * Reads the workspace's locale (VISION Layer 1) and provides it to the app.
 * Sits under QueryClientProvider so useWorkspace works; before the workspace
 * loads (or on the login screen) it resolves to the default locale.
 */
function LocalizedApp() {
  const { data: workspace } = useWorkspace();
  return (
    <I18nProvider locale={workspace?.ui_config?.locale}>
      <App />
    </I18nProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <LocalizedApp />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
