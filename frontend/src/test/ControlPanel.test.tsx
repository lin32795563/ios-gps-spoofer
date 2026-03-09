/**
 * Tests for the ControlPanel component (multi-select version).
 *
 * Verifies:
 * - Conditional rendering based on selection count
 * - Speed preset and slider controls
 * - Simulation state-dependent button rendering
 * - Progress display
 * - Favorite management
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ControlPanel } from "../components/ControlPanel";
import type {
  DeviceSessionState,
  FavoriteLocation,
  SimulationProgress,
} from "../types/api";
import { createDefaultSession } from "../types/api";

function makeProgress(
  overrides: Partial<SimulationProgress> = {},
): SimulationProgress {
  return {
    current_position: { latitude: 37.0, longitude: -122.0 },
    segment_index: 2,
    total_segments: 10,
    distance_covered_m: 500,
    total_distance_m: 2000,
    fraction_complete: 0.25,
    elapsed_time_s: 120,
    speed_ms: 1.39,
    state: "running",
    ...overrides,
  };
}

const defaultHandlers = {
  onStartSimulation: vi.fn(),
  onPause: vi.fn(),
  onResume: vi.fn(),
  onStop: vi.fn(),
  onSpeedChange: vi.fn(),
  onClearLocation: vi.fn(),
  onToggleDrawPath: vi.fn(),
  onClearPath: vi.fn(),
  onGPXLoad: vi.fn(),
  onAddFavorite: vi.fn(),
  onRemoveFavorite: vi.fn(),
  onSelectFavorite: vi.fn(),
};

const baseProps = {
  selectedCount: 0,
  anyDeviceReady: false,
  simState: "idle" as const,
  simProgress: null as SimulationProgress | null,
  speedKmh: 5,
  isDrawingPath: false,
  pathPointCount: 0,
  favorites: [] as FavoriteLocation[],
  deviceSessions: new Map<string, DeviceSessionState>(),
  selectedUdids: new Set<string>(),
  ...defaultHandlers,
};

beforeEach(() => {
  Object.values(defaultHandlers).forEach((fn) => fn.mockClear());
});

describe("ControlPanel", () => {
  describe("no device selected", () => {
    it("should show prompt to select device", () => {
      render(<ControlPanel {...baseProps} />);

      expect(screen.getByText("請先選擇裝置")).toBeInTheDocument();
    });

    it("should not show simulation controls", () => {
      render(<ControlPanel {...baseProps} />);

      expect(screen.queryByText("恢復真實定位")).toBeNull();
      expect(screen.queryByText("開始模擬")).toBeNull();
    });
  });

  describe("device selected but not ready", () => {
    it("should show warning when devices are not ready", () => {
      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={false}
        />,
      );

      expect(screen.getByText("所選裝置尚未就緒")).toBeInTheDocument();
    });
  });

  describe("selected count display", () => {
    it("should display selected count", () => {
      render(
        <ControlPanel
          {...baseProps}
          selectedCount={3}
          anyDeviceReady={true}
        />,
      );

      expect(screen.getByText("已選 3 台裝置")).toBeInTheDocument();
    });
  });

  describe("location controls", () => {
    it("should render restore button", () => {
      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
        />,
      );

      expect(screen.getByText("恢復真實定位")).toBeInTheDocument();
    });

    it("should call onClearLocation when clicked", async () => {
      const user = userEvent.setup();

      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
        />,
      );

      await user.click(screen.getByText("恢復真實定位"));
      expect(defaultHandlers.onClearLocation).toHaveBeenCalled();
    });

    it("should disable restore button during simulation", () => {
      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
          simState="running"
          simProgress={makeProgress()}
        />,
      );

      expect(screen.getByText("恢復真實定位")).toBeDisabled();
    });
  });

  describe("path drawing", () => {
    it("should show draw path button", () => {
      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
        />,
      );

      expect(screen.getByText("繪製路徑")).toBeInTheDocument();
    });

    it("should show end drawing when drawing", () => {
      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
          isDrawingPath={true}
          pathPointCount={3}
        />,
      );

      expect(screen.getByText("結束繪製")).toBeInTheDocument();
    });

    it("should show point count when path has points", () => {
      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
          pathPointCount={5}
        />,
      );

      expect(screen.getByText(/5 個路徑點/)).toBeInTheDocument();
    });

    it("should call onClearPath when clear path is clicked", async () => {
      const user = userEvent.setup();

      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
          pathPointCount={3}
        />,
      );

      await user.click(screen.getByText("清除路徑"));
      expect(defaultHandlers.onClearPath).toHaveBeenCalled();
    });
  });

  describe("speed controls", () => {
    it("should display current speed", () => {
      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
          speedKmh={15}
        />,
      );

      expect(screen.getByText(/15\.0 km\/h/)).toBeInTheDocument();
    });

    it("should render speed preset buttons", () => {
      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
        />,
      );

      expect(screen.getByText("步行")).toBeInTheDocument();
      expect(screen.getByText("騎車")).toBeInTheDocument();
      expect(screen.getByText("開車")).toBeInTheDocument();
      expect(screen.getByText("高速")).toBeInTheDocument();
    });

    it("should call onSpeedChange when preset is clicked", async () => {
      const user = userEvent.setup();

      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
        />,
      );

      await user.click(screen.getByText("騎車"));
      expect(defaultHandlers.onSpeedChange).toHaveBeenCalledWith(15);
    });
  });

  describe("simulation controls", () => {
    it("should show start button in idle state", () => {
      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
          pathPointCount={5}
        />,
      );

      expect(screen.getByText("開始模擬")).toBeInTheDocument();
    });

    it("should disable start when less than 2 path points", () => {
      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
          pathPointCount={1}
        />,
      );

      expect(screen.getByText("開始模擬")).toBeDisabled();
    });

    it("should show pause and stop during running", () => {
      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
          simState="running"
          simProgress={makeProgress()}
          pathPointCount={5}
        />,
      );

      expect(screen.getByText("暫停")).toBeInTheDocument();
      expect(screen.getByText("停止")).toBeInTheDocument();
    });

    it("should show resume and stop when paused", () => {
      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
          simState="paused"
          simProgress={makeProgress({ state: "paused" })}
          pathPointCount={5}
        />,
      );

      expect(screen.getByText("繼續")).toBeInTheDocument();
      expect(screen.getByText("停止")).toBeInTheDocument();
    });

    it("should show restart button on completed", () => {
      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
          simState="completed"
          pathPointCount={5}
        />,
      );

      expect(screen.getByText("重新開始")).toBeInTheDocument();
    });

    it("should show retry button on error", () => {
      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
          simState="error"
          pathPointCount={5}
        />,
      );

      expect(screen.getByText("重試模擬")).toBeInTheDocument();
    });

    it("should call onStartSimulation when start clicked", async () => {
      const user = userEvent.setup();

      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
          pathPointCount={5}
        />,
      );

      await user.click(screen.getByText("開始模擬"));
      expect(defaultHandlers.onStartSimulation).toHaveBeenCalled();
    });

    it("should call onPause when pause clicked", async () => {
      const user = userEvent.setup();

      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
          simState="running"
          simProgress={makeProgress()}
          pathPointCount={5}
        />,
      );

      await user.click(screen.getByText("暫停"));
      expect(defaultHandlers.onPause).toHaveBeenCalled();
    });
  });

  describe("progress display", () => {
    it("should show progress bar and details when simulation active", () => {
      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
          simState="running"
          simProgress={makeProgress({
            fraction_complete: 0.5,
            elapsed_time_s: 300,
            distance_covered_m: 1500,
            total_distance_m: 3000,
            segment_index: 5,
            total_segments: 10,
          })}
          pathPointCount={5}
        />,
      );

      expect(screen.getByText("50.0%")).toBeInTheDocument();
      expect(screen.getByText("05:00")).toBeInTheDocument();
      expect(screen.getByText(/1\.50km/)).toBeInTheDocument();
    });

    it("should not show progress when simProgress is null", () => {
      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
        />,
      );

      expect(screen.queryByText("模擬進度")).toBeNull();
    });
  });

  describe("device progress summary", () => {
    it("should show per-device progress when multiple devices selected", () => {
      const sessions = new Map<string, DeviceSessionState>();
      sessions.set("udid-aaaa1111", { ...createDefaultSession(), simState: "running", simProgress: makeProgress({ fraction_complete: 0.3 }) });
      sessions.set("udid-bbbb2222", { ...createDefaultSession(), simState: "paused" });

      render(
        <ControlPanel
          {...baseProps}
          selectedCount={2}
          anyDeviceReady={true}
          simState="running"
          deviceSessions={sessions}
          selectedUdids={new Set(["udid-aaaa1111", "udid-bbbb2222"])}
        />,
      );

      expect(screen.getByText("各裝置進度")).toBeInTheDocument();
      expect(screen.getByText("...aaaa1111")).toBeInTheDocument();
      expect(screen.getByText("...bbbb2222")).toBeInTheDocument();
    });
  });

  describe("favorites", () => {
    it("should show empty state when no favorites", () => {
      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
        />,
      );

      expect(screen.getByText("尚無收藏地點")).toBeInTheDocument();
    });

    it("should render favorite locations", () => {
      const favorites: FavoriteLocation[] = [
        { name: "Home", latitude: 37.0, longitude: -122.0 },
        { name: "Work", latitude: 37.5, longitude: -122.5 },
      ];

      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
          favorites={favorites}
        />,
      );

      expect(screen.getByText("Home")).toBeInTheDocument();
      expect(screen.getByText("Work")).toBeInTheDocument();
    });

    it("should call onSelectFavorite when favorite clicked", async () => {
      const user = userEvent.setup();
      const fav = { name: "Home", latitude: 37.0, longitude: -122.0 };

      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
          favorites={[fav]}
        />,
      );

      await user.click(screen.getByText("Home"));
      expect(defaultHandlers.onSelectFavorite).toHaveBeenCalledWith(fav);
    });

    it("should call onRemoveFavorite when X clicked", async () => {
      const user = userEvent.setup();
      const fav = { name: "Home", latitude: 37.0, longitude: -122.0 };

      render(
        <ControlPanel
          {...baseProps}
          selectedCount={1}
          anyDeviceReady={true}
          favorites={[fav]}
        />,
      );

      await user.click(screen.getByLabelText("刪除 Home"));
      expect(defaultHandlers.onRemoveFavorite).toHaveBeenCalledWith(fav);
    });
  });
});
