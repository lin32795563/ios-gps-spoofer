/**
 * React application entry point.
 *
 * Renders the root App component into the DOM and imports global
 * MapLibre GL CSS required for correct map rendering.
 */

import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "maplibre-gl/dist/maplibre-gl.css";
import "./App.css";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error(
    "Root element not found. Ensure index.html contains a <div id='root'>.",
  );
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
