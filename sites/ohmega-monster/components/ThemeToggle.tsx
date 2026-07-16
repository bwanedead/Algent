"use client";

import { useEffect, useState } from "react";

type DisplayTheme = "dark-amber" | "paper";

// A display preference, not a separate brand skin. The layout's no-flash script applies the
// persisted value before paint so both modes stay stable across navigation.
export default function ThemeToggle() {
  const [theme, setTheme] = useState<DisplayTheme>("dark-amber");

  useEffect(() => {
    const current = document.documentElement.getAttribute("data-theme");
    setTheme(current === "paper" ? "paper" : "dark-amber");
  }, []);

  function toggle() {
    const next: DisplayTheme = document.documentElement.getAttribute("data-theme") === "paper" ? "dark-amber" : "paper";
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
      aria-label={`Switch to ${theme === "dark-amber" ? "paper" : "dark amber"} display`}
      title={`Switch to ${theme === "dark-amber" ? "paper" : "dark amber"} display`}
    >
      <span className="display-label">Display</span>
      <span>{theme === "dark-amber" ? "Dark amber" : "Paper"}</span>
    </button>
  );
}
