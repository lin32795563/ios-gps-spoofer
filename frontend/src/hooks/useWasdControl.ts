import { useEffect, useRef, useState } from "react";
import type { Coordinate } from "../types/api";

export const TICK_MS = 150;
const WASD_KEYS = ["w", "a", "s", "d"] as const;

interface UseWasdControlOptions {
  isActive: boolean;
  stepMeters: number;
  currentPosRef: React.RefObject<Coordinate | null>;
  onMove: (deltaLat: number, deltaLng: number) => void;
}

export function useWasdControl({
  isActive,
  stepMeters,
  currentPosRef,
  onMove,
}: UseWasdControlOptions): Set<string> {
  const [pressedKeys, setPressedKeys] = useState<Set<string>>(new Set());
  const heldKeys = useRef<Set<string>>(new Set());
  const onMoveRef = useRef(onMove);
  onMoveRef.current = onMove;
  const stepMetersRef = useRef(stepMeters);
  stepMetersRef.current = stepMeters;

  useEffect(() => {
    if (!isActive) {
      heldKeys.current.clear();
      setPressedKeys(new Set());
      return;
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();
      if (!(WASD_KEYS as readonly string[]).includes(key)) return;
      e.preventDefault();
      if (!heldKeys.current.has(key)) {
        heldKeys.current.add(key);
        setPressedKeys(new Set(heldKeys.current));
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();
      if (heldKeys.current.has(key)) {
        heldKeys.current.delete(key);
        setPressedKeys(new Set(heldKeys.current));
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);

    const interval = setInterval(() => {
      const keys = heldKeys.current;
      if (keys.size === 0) return;

      const pos = currentPosRef.current;
      const lat = pos?.latitude ?? 0;
      const step = stepMetersRef.current;
      const metersPerDegLat = 111320;
      const metersPerDegLng = 111320 * Math.cos((lat * Math.PI) / 180);

      let deltaLat = 0;
      let deltaLng = 0;

      if (keys.has("w")) deltaLat += step / metersPerDegLat;
      if (keys.has("s")) deltaLat -= step / metersPerDegLat;
      if (keys.has("d")) deltaLng += step / metersPerDegLng;
      if (keys.has("a")) deltaLng -= step / metersPerDegLng;

      if (deltaLat !== 0 || deltaLng !== 0) {
        onMoveRef.current(deltaLat, deltaLng);
      }
    }, TICK_MS);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
      clearInterval(interval);
      heldKeys.current.clear();
      setPressedKeys(new Set());
    };
  }, [isActive, currentPosRef]);

  return pressedKeys;
}
