import "@testing-library/jest-dom/vitest";

// jsdom has no matchMedia; report "light" so ModeToggle can read the OS preference.
window.matchMedia = (query) =>
  ({
    matches: false,
    media: query,
    addEventListener() {},
    removeEventListener() {},
  }) as unknown as MediaQueryList;
