/**
 * Vitest test setup file.
 *
 * Configures jsdom environment extensions (jest-dom matchers)
 * and mocks browser APIs not available in the test environment.
 */

import "@testing-library/jest-dom/vitest";

// Mock ResizeObserver (used by MapLibre GL but not available in jsdom)
class MockResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver = MockResizeObserver as unknown as typeof ResizeObserver;

// Mock matchMedia (used by some UI libraries)
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});
