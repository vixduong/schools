import { useState } from "react";
import { Button } from "@/components/ui/button";

type Mode = "light" | "dark";

// With no stored choice the page follows the OS (tokens.css), so read what is showing now.
function currentMode(): Mode {
  const set = document.documentElement.dataset.mode;
  if (set === "light" || set === "dark") return set;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ModeToggle() {
  const [mode, setMode] = useState(currentMode);
  const next: Mode = mode === "dark" ? "light" : "dark";

  function toggle() {
    document.documentElement.dataset.mode = next;
    try {
      localStorage.setItem("mode", next);
    } catch {
      // storage blocked: the choice lasts for this page only
    }
    setMode(next);
  }

  return (
    <Button variant="secondary" onClick={toggle} aria-pressed={mode === "dark"}>
      {mode === "dark" ? "Chế độ sáng" : "Chế độ tối"}
    </Button>
  );
}
