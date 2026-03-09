# iOS GPS Spoofer

A desktop application for simulating GPS location on iOS devices. Built with **Electron + React + TypeScript** (frontend) and **Python FastAPI** (backend), communicating over REST API and WebSocket.

Supports **iOS 14–18**, including iOS 17+ RemoteXPC tunnel mode.

---

## Features

- **Teleport** — Instantly set your iPhone's GPS to any location by clicking on the map
- **Path Simulation** — Draw a custom route or import a GPX file, then simulate continuous movement with realistic GPS drift
- **Multi-device Support** — Connect and simultaneously control multiple iPhones from a single interface
- **Speed Control** — Preset profiles (Walk / Bike / Drive / Highway) or a custom slider from 1–200 km/h
- **GPX Import** — Import standard GPX files for precise route recreation
- **Favorites** — Save and quickly access frequently used locations
- **Real-time Map** — OpenStreetMap-based map with coordinate search and place name geocoding
- **Live Status** — WebSocket-powered real-time simulation progress per device

---

## Requirements

| Item | Details |
|------|---------|
| OS | Windows 10 or later |
| iPhone | iOS 14 or later |
| Connection | USB cable (Lightning or USB-C) |
| Software | iTunes (for Apple Mobile Device USB drivers) |
| Python | 3.11 or later |
| Node.js | 18 or later |

---

## Installation

### 1. Install iTunes

Install iTunes from the [Microsoft Store](https://apps.microsoft.com/store/detail/itunes/9PB2MZ1ZMB1S) or [Apple's website](https://www.apple.com/itunes/). The USB drivers are required for device detection — iTunes itself does not need to be running.

### 2. Install Python Dependencies

```bash
cd backend
pip install -e .
```

> Core dependency: [`pymobiledevice3`](https://github.com/doronz88/pymobiledevice3)

### 3. Install Frontend Dependencies

```bash
cd frontend
npm install
```

---

## Setup

### iPhone Configuration

1. Connect your iPhone via USB
2. Tap **Trust** on the device when prompted, then enter your passcode
3. **iOS 16+**: Go to **Settings → Privacy & Security → Developer Mode** and enable it

### iOS 17+ Additional Step — Start Tunneld

Open a terminal **as Administrator** and run:

```bash
pymobiledevice3 remote tunneld
```

Keep this window open while using the app. This is only required for iOS 17 and later; iOS 14–16 users can skip this step.

---

## Running the App

```bash
cd frontend
npm run electron:start
```

The backend server starts automatically on `http://127.0.0.1:8456`.

---

## Usage

### Teleport

1. Select one or more iPhones from the device panel (left side)
2. Click any location on the map
3. Click **Teleport Here** in the popup

### Path Simulation

1. Click **Draw Path** and place waypoints on the map (minimum 2 points)
2. Click **Finish Drawing**
3. Select a speed preset or adjust the slider
4. Click **Start Simulation**

All selected devices will follow the same path simultaneously.

| Preset | Speed |
|--------|-------|
| Walk | 5 km/h |
| Bike | 15 km/h |
| Drive | 60 km/h |
| Highway | 120 km/h |

To import an existing route, click **Import GPX** and select a `.gpx` file.

### Multi-device Control

- Use the checkboxes in the device panel to select multiple iPhones
- Use **Select All / Deselect All** for bulk selection
- All simulation controls (teleport, start, pause, stop) apply to every selected device simultaneously
- Each device's real-time progress is shown individually in the control panel

### Search

Use the search bar (top-right of the map) to find locations by:
- **Place name** — e.g., `Shibuya`, `Taipei 101`
- **Coordinates** — e.g., `25.033964, 121.564468`

### Restoring Real Location

| Method | How |
|--------|-----|
| Button | Click **Restore Real Location** in the control panel |
| Unplug | Disconnect the USB cable (location restores within seconds) |
| Restart | Restart the iPhone |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Electron, React, TypeScript, Vite |
| Map | MapLibre GL, OpenFreeMap (no API key required) |
| Backend | Python, FastAPI, uvicorn |
| Device | pymobiledevice3 |
| Communication | REST API, WebSocket |
| Simulation | Per-device threaded PathSimulator with GPS drift |

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/devices` | List connected devices |
| POST | `/api/location/set` | Set GPS location |
| POST | `/api/location/clear` | Restore real GPS |
| POST | `/api/simulation/start` | Start path simulation |
| POST | `/api/simulation/pause` | Pause simulation |
| POST | `/api/simulation/resume` | Resume simulation |
| POST | `/api/simulation/stop` | Stop simulation |
| WS | `/ws` | Real-time simulation updates |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Device not detected | Check USB cable, trust the computer on the device, ensure iTunes drivers are installed; for iOS 17+, confirm `tunneld` is running as Administrator |
| Teleport not working | Ensure the device status shows green; if DVT session times out, stop and retry |
| Map not loading | Check your internet connection and firewall — map tiles are served from `tiles.openfreemap.org` |
| GPS snaps back to real location | Use realistic speeds and avoid pausing simulation for extended periods |
| iOS 17 tunnel error | Restart `tunneld` as Administrator; ensure no other tunnel process is already running |

---

## Support

If this tool has been helpful to you, consider buying me a coffee — it keeps the development going!

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-☕%20Support-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/yannis_lin)

Sponsorship is entirely voluntary and does not affect access to any features.

---

## License

MIT
