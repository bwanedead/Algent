"use client";

import { useEffect, useState } from "react";

// Minimal off-white / dark toggle. Persists to localStorage; the no-flash script in the layout
// sets the initial theme before paint.
export default function ThemeToggle() {
  const [theme, setTheme] = useState<string>("");

  useEffect(() => {
    setTheme(document.documentElement.getAttribute("data-theme") || "");
  }, []);

  function toggle() {
    const next = (document.documentElement.getAttribute("data-theme") || "light") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("theme", next);
    } catch {}
    setTheme(next);
  }

  return (
    <button className="themebtn" onClick={toggle} aria-label="Toggle color theme">
      {theme === "dark" ? "light" : "dark"} mode
    </button>
  );
}
