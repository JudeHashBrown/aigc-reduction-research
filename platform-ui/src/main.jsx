import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.jsx";
import { LocaleProvider } from "./locale.jsx";
import { PlatformProvider } from "./platform.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <LocaleProvider>
      <PlatformProvider>
        <App />
      </PlatformProvider>
    </LocaleProvider>
  </React.StrictMode>,
);
