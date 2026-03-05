# iOS GPS Spoofer

A desktop application for spoofing GPS location on iOS devices. Built with **Electron + React** (frontend) and **Python FastAPI** (backend).

Supports iOS 14–18, including iOS 17+ tunnel mode.

## Features

- **Teleport** — Click anywhere on the map to instantly set your iPhone's GPS location
- **Path Simulation** — Draw a route or import a GPX file, then simulate movement at walking, cycling, or driving speed
- **Search** — Search by place name or coordinates
- **Favorites** — Save frequently used locations for quick access
- **Multi-device** — Detect and manage multiple connected iPhones

## Requirements

| Item | Details |
|------|---------|
| OS | Windows 10+ |
| iPhone | iOS 14+ |
| Connection | USB cable (Lightning or USB-C) |
| Software | iTunes (for USB drivers) |
| Network | Required (map tiles) |

## Setup

### 1. Install iTunes

Install iTunes from the Microsoft Store or Apple's website. The USB driver is needed for device detection — you don't need to open iTunes itself.

### 2. iPhone Settings

1. **Settings > Privacy & Security > Developer Mode** → Enable (iOS 16+ only)
2. Connect iPhone via USB
3. Tap **Trust** when prompted, then enter your passcode

### 3. Start Tunneld (iOS 17+ only)

Open a terminal **as Administrator** and run:

```bash
pymobiledevice3 remote tunneld
```

Keep this window open while using the app. Not required for iOS 14–16.

### 4. Launch the App

In a separate terminal:

```bash
cd frontend
npm run electron:start
```

## Usage

### Teleport

1. Select your iPhone from the device list (left panel)
2. Click a location on the map
3. Click **"Teleport Here"**

### Path Simulation

1. Click **"Draw Path"** and place waypoints on the map (minimum 2 points)
2. Click **"Finish Drawing"**
3. Choose a speed preset or use the slider (1–200 km/h)
4. Click **"Start Simulation"**

| Preset | Speed |
|--------|-------|
| Walk | 5 km/h |
| Bike | 15 km/h |
| Drive | 60 km/h |
| Highway | 120 km/h |

You can also import a `.gpx` file instead of drawing manually.

### Search

Use the search bar (top-right) to search by:
- **Place name** — e.g., `Tokyo Tower`, `Times Square`
- **Coordinates** — e.g., `25.033964, 121.564468`

### Favorites

In the **Favorites** section of the control panel:
- Enter a name + coordinates → click **Add**
- Click a saved favorite to teleport instantly
- Click **X** to delete

### Restore Real Location

| Method | How |
|--------|-----|
| Button | Click **"Restore Real Location"** in the control panel |
| Unplug | Disconnect the USB cable (GPS restores in seconds) |
| Restart | Restart the iPhone |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| iPhone not detected | Check USB cable, trust the computer, install iTunes, run tunneld for iOS 17+ |
| Teleport not working | Select a device first, wait for green status, retry if DVT times out |
| Map not loading | Check internet connection and firewall (`tiles.openfreemap.org`) |
| GPS jumps back to real location | Avoid long pauses during simulation; use realistic speeds |

## Tech Stack

- **Frontend**: Electron + React + TypeScript + Vite + Leaflet
- **Backend**: Python + FastAPI + pymobiledevice3
- **Communication**: REST API + WebSocket

| Service | URL |
|---------|-----|
| Backend API | `http://127.0.0.1:8456` |
| WebSocket | `ws://127.0.0.1:8456/ws` |
| Frontend (dev) | `http://localhost:5173` |
