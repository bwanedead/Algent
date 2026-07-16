"use client";

import { useEffect, useState } from "react";

type DisplayTheme = "terminal" | "paper";

// A display preference, not a separate brand skin. The layout's no-flash script applies the
// persisted value before paint so both modes stay stable across navigation.
export default function ThemeToggle() {
  const [theme, setTheme] = useState<DisplayTheme>("terminal");

  useEffect(() => {
    const current = document.documentElement.getAttribute("data-theme");
    setTheme(current === "paper" ? "paper" : "terminal");
  }, []);

  function toggle() {
    const next: DisplayTheme = document.documentElement.getAttribute("data-theme") === "paper" ? "terminal" : "paper";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("theme", next);
    } catch {}
    setTheme(next);
  }

  return (
    <button
      className="display-toggle"
      onClick={toggle}
      aria-label={`Switch to ${theme === "terminal" ? "paper" : "amber terminal"} display`}
      title={`Switch to ${theme === "terminal" ? "paper" : "amber terminal"} display`}
    >
      <span className="display-label">Display</span>
      <span>{theme === "terminal" ? "Amber" : "Paper"}</span>
    </button>
  );
}
