/**
 * Electron preload script.
 *
 * Exposes a safe API to the renderer process via contextBridge.
 * The renderer uses window.electronAPI to get the backend URL
 * and WebSocket URL without needing nodeIntegration.
 */

import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("electronAPI", {
  getApiUrl: (): Promise<string> => ipcRenderer.invoke("get-api-url"),
  getWsUrl: (): Promise<string> => ipcRenderer.invoke("get-ws-url"),
});
