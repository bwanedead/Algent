"use client";

import { useEffect, useState, type ReactNode } from "react";

import "./hubs.css";

// One tab per desk. Every panel is rendered on the server and is in the page's HTML (search engines and no-script readers see all
// of them); the tabs only choose which one is visible. The tab is also the URL hash (#ai), so a desk can be linked to and survives
// a reload. With no hash, the first tab opens.
export type DeskTab = { id: string; label: string; count: string; panel: ReactNode };

export default function DeskTabs({ tabs }: { tabs: DeskTab[] }) {
  const [on, setOn] = useState(tabs[0]?.id ?? "");
  useEffect(() => {
    const fromHash = () => {
      const h = window.location.hash.replace(/^#/, "");
      if (tabs.some((t) => t.id === h)) setOn(h);
    };
    fromHash();
    window.addEventListener("hashchange", fromHash);
    return () => window.removeEventListener("hashchange", fromHash);
  }, [tabs]);
  const pick = (id: string) => {
    setOn(id);
    try {
      window.history.replaceState(null, "", `#${id}`);
    } catch {
      /* the tab still switches without a URL update */
    }
  };
  return (
    <>
      <div className="hub-tabs" role="tablist" aria-label="Desks">
        {tabs.map((t) => (
          <button key={t.id} type="button" role="tab" id={`tab-${t.id}`} aria-controls={`panel-${t.id}`} aria-selected={on === t.id} className="hub-tab" onClick={() => pick(t.id)}>
            {t.label}
            <span className="hub-tab-n">{t.count}</span>
          </button>
        ))}
      </div>
      {tabs.map((t) => (
        <div key={t.id} role="tabpanel" id={`panel-${t.id}`} aria-labelledby={`tab-${t.id}`} hidden={on !== t.id}>
          {t.panel}
        </div>
      ))}
    </>
  );
}
