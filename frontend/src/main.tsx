import './index.css'
import React from "react";
import ReactDOM from "react-dom/client";
import App from './App.tsx'
import MemoryNavigationProvider from "./context/MemoryNavigationProvider";

ReactDOM.createRoot(
  document.getElementById("root")!
).render(
  <React.StrictMode>
    <MemoryNavigationProvider>
      <App />
    </MemoryNavigationProvider>
  </React.StrictMode>
);