/**
 * Electron main process.
 *
 * Responsibilities:
 * - Create the BrowserWindow
 * - Check that tunneld is running (required for iOS 17+)
 * - Start the Python backend as a child process
 * - Wait for the backend to be healthy before loading the UI
 * - Gracefully shut down the backend on app quit
 *
 * Startup order:
 * 1. Check tunneld at 127.0.0.1:49151 (warn if not running)
 * 2. Start Python backend (FastAPI server)
 * 3. Wait for backend health check
 * 4. Create and show the UI window
 */

import { app, BrowserWindow, ipcMain, dialog } from "electron";
import { ChildProcess, spawn } from "child_process";
import * as path from "path";
import * as http from "http";

const API_HOST = "127.0.0.1";
const API_PORT = 8456;
const HEALTH_CHECK_URL = `http://${API_HOST}:${API_PORT}/api/health`;
const HEALTH_CHECK_INTERVAL_MS = 500;
const HEALTH_CHECK_TIMEOUT_MS = 30000;

const TUNNELD_HOST = "127.0.0.1";
const TUNNELD_PORT = 49151;
const TUNNELD_URL = `http://${TUNNELD_HOST}:${TUNNELD_PORT}`;

let mainWindow: BrowserWindow | null = null;
let backendProcess: ChildProcess | null = null;
let tunneldProcess: ChildProcess | null = null;
let isQuitting = false;

/**
 * Find the Python executable in the project's virtual environment.
 */
function findPythonPath(): string {
  const projectRoot = path.resolve(__dirname, "..", "..");
  const isWin = process.platform === "win32";
  const venvPython = isWin
    ? path.join(projectRoot, ".venv", "Scripts", "python.exe")
    : path.join(projectRoot, ".venv", "bin", "python");
  return venvPython;
}

/**
 * Find the pymobiledevice3 executable in the project's virtual environment.
 */
function findPymobiledevice3Path(): string {
  const projectRoot = path.resolve(__dirname, "..", "..");
  const isWin = process.platform === "win32";
  return isWin
    ? path.join(projectRoot, ".venv", "Scripts", "pymobiledevice3.exe")
    : path.join(projectRoot, ".venv", "bin", "pymobiledevice3");
}

/**
 * Start tunneld as a managed child process.
 */
function startTunneld(): void {
  const pymobilePath = findPymobiledevice3Path();
  tunneldProcess = spawn(pymobilePath, ["remote", "tunneld"], {
    stdio: "ignore",
    windowsHide: true,
  });
  tunneldProcess.on("error", (err) => {
    console.error("Failed to start tunneld:", err.message);
  });
  tunneldProcess.on("exit", (code) => {
    if (!isQuitting) {
      console.warn(`tunneld exited unexpectedly (code ${code})`);
    }
    tunneldProcess = null;
  });
  console.log("tunneld started (pid:", tunneldProcess.pid, ")");
}

/**
 * Stop the tunneld process.
 */
function stopTunneld(): void {
  if (tunneldProcess && !tunneldProcess.killed) {
    tunneldProcess.kill();
    tunneldProcess = null;
    console.log("tunneld stopped");
  }
}

/**
 * Check if tunneld is running at 127.0.0.1:49151.
 * This is required for iOS 17+ device support.
 */
function checkTunneld(): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get(TUNNELD_URL, (res) => {
      resolve(res.statusCode === 200);
    });
    req.on("error", () => resolve(false));
    req.setTimeout(3000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

/**
 * Start the Python backend server as a child process.
 */
function startBackend(): ChildProcess {
  const pythonPath = findPythonPath();
  const projectRoot = path.resolve(__dirname, "..", "..");

  console.log(`Starting backend: ${pythonPath} -m ios_gps_spoofer.api.server`);

  const proc = spawn(pythonPath, ["-m", "ios_gps_spoofer.api.server"], {
    cwd: path.join(projectRoot, "backend", "src"),
    env: {
      ...process.env,
      PYTHONPATH: path.join(projectRoot, "backend", "src"),
      PYTHONUNBUFFERED: "1",
    },
    stdio: ["pipe", "pipe", "pipe"],
  });

  proc.stdout?.on("data", (data: Buffer) => {
    console.log(`[backend] ${data.toString().trim()}`);
  });

  proc.stderr?.on("data", (data: Buffer) => {
    console.error(`[backend] ${data.toString().trim()}`);
  });

  proc.on("error", (err: Error) => {
    console.error("Failed to start backend:", err.message);
  });

  proc.on("exit", (code: number | null) => {
    if (!isQuitting) {
      console.error(`Backend exited unexpectedly with code ${code}`);
    }
    backendProcess = null;
  });

  return proc;
}

/**
 * Check if the backend health endpoint responds.
 */
function checkHealth(): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get(HEALTH_CHECK_URL, (res) => {
      resolve(res.statusCode === 200);
    });
    req.on("error", () => resolve(false));
    req.setTimeout(2000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

/**
 * Wait for the backend to become healthy.
 */
async function waitForBackend(): Promise<boolean> {
  const startTime = Date.now();
  while (Date.now() - startTime < HEALTH_CHECK_TIMEOUT_MS) {
    const healthy = await checkHealth();
    if (healthy) {
      console.log("Backend is healthy");
      return true;
    }
    await new Promise((r) => setTimeout(r, HEALTH_CHECK_INTERVAL_MS));
  }
  console.error("Backend health check timed out");
  return false;
}

/**
 * Stop the backend process gracefully.
 */
function stopBackend(): void {
  if (backendProcess && !backendProcess.killed) {
    console.log("Stopping backend...");
    // On Windows, SIGTERM is not supported; use taskkill or just kill
    if (process.platform === "win32") {
      // Send SIGTERM equivalent
      backendProcess.kill();
    } else {
      backendProcess.kill("SIGTERM");
    }
    // Force kill after timeout
    setTimeout(() => {
      if (backendProcess && !backendProcess.killed) {
        console.log("Force killing backend...");
        backendProcess.kill("SIGKILL");
      }
    }, 5000);
  }
}

/**
 * Create the main application window.
 */
function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 700,
    title: "iOS GPS Spoofer",
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "preload.js"),
    },
    show: false,
  });

  // Determine which URL to load.
  // Use VITE_DEV_SERVER env var (set by electron:dev script) to detect dev mode.
  // Otherwise load from built renderer files.
  const viteDevUrl = process.env.VITE_DEV_SERVER_URL;
  if (viteDevUrl) {
    mainWindow.loadURL(viteDevUrl);
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));
  }

  mainWindow.once("ready-to-show", () => {
    mainWindow?.show();
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// ------------------------------------------------------------------
// IPC handlers
// ------------------------------------------------------------------

ipcMain.handle("get-api-url", () => {
  return `http://${API_HOST}:${API_PORT}`;
});

ipcMain.handle("get-ws-url", () => {
  return `ws://${API_HOST}:${API_PORT}/ws`;
});

// ------------------------------------------------------------------
// App lifecycle
// ------------------------------------------------------------------

app.on("ready", async () => {
  // Step 1: Start tunneld (if not already running externally)
  const tunneldRunning = await checkTunneld();
  if (tunneldRunning) {
    console.log("tunneld already running at " + TUNNELD_URL);
  } else {
    startTunneld();
    // Give tunneld a moment to initialize
    await new Promise((r) => setTimeout(r, 2000));
  }

  // Step 2: Start backend
  backendProcess = startBackend();

  // Step 3: Wait for backend health check
  const healthy = await waitForBackend();
  if (!healthy) {
    console.error("Could not start backend. Exiting.");
    app.quit();
    return;
  }

  // Step 4: Create window
  createWindow();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("activate", () => {
  if (mainWindow === null) {
    createWindow();
  }
});

app.on("before-quit", () => {
  isQuitting = true;
  stopBackend();
  stopTunneld();
});
