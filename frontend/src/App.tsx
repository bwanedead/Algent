import { useEffect, useMemo, useState } from "react";
import SettingsTray from "./components/SettingsTray";
import GridTraceLayer from "./components/GridTraceLayer";
import ModuleGrid from "./components/ModuleGrid";
import { GridProvider } from "./context/GridContext";
import { ModuleDraft, ModuleShape } from "./types/modules";

const App = () => {
  const [modules, setModules] = useState<ModuleShape[]>([]);
  const [placementMode, setPlacementMode] = useState(false);
  const [maskDebug, setMaskDebug] = useState(false);

  const handleModuleCreate = (draft: ModuleDraft) => {
    setModules((prev) => [
      ...prev,
      {
        id: crypto.randomUUID ? crypto.randomUUID() : `module-${Date.now()}`,
        name: `Module ${prev.length + 1}`,
        ...draft,
      },
    ]);
    setPlacementMode(false);
  };

  const handleModuleDelete = (id: string) => {
    setModules((prev) => prev.filter((module) => module.id != id));
  };

  const moduleCountLabel = useMemo(
    () => `${modules.length.toString().padStart(2, "0")} modules`,
    [modules.length],
  );

  const handleMouseMove = (e: React.MouseEvent) => {
    const el = e.currentTarget as HTMLElement;
    el.style.setProperty("--cursor-x", `${e.clientX}px`);
    el.style.setProperty("--cursor-y", `${e.clientY}px`);
  };

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (event.altKey && event.key.toLowerCase() === "m") {
        setMaskDebug((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  useEffect(() => {
    document.documentElement.style.setProperty(
      "--hud-mask-debug-radius",
      maskDebug ? "2000px" : "0px",
    );
  }, [maskDebug]);

  return (
    <GridProvider>
      <div className="hud-shell" onMouseMove={handleMouseMove}>
        <div className="hud-noise" aria-hidden="true" />
        <div className="hud-scanlines" aria-hidden="true" />

        {/* Global Snap Grid Layers */}
        <div className="hud-grid-layer base-grid" aria-hidden="true" />
        <div className="hud-grid-layer micro-grid" aria-hidden="true" />
        <div className="hud-grid-layer meta-grid" aria-hidden="true" />

        {/* Random Pulse Traces */}
        <GridTraceLayer />

        {/* Side Settings Tray */}
        <SettingsTray />

        <div className="hud-frame">
          <header className="hud-header">
            <div className="hud-title-block">
              <div className="hud-label">sys.id: 0x9281</div>
              <div className="hud-title">ALGENT::CTRL</div>
              <div className="hud-label">{moduleCountLabel}</div>
            </div>
            <div className="hud-status-block">
              <div className="hud-label">NET</div>
              <div className="hud-value hud-value--online">ACTIVE</div>
            </div>
            <div className="hud-actions">
              <button
                className={`hud-button ${placementMode ? "is-active" : ""}`}
                type="button"
                onClick={() => setPlacementMode((previous) => !previous)}
              >
                {placementMode ? "Cancel placement" : "New Module"}
              </button>
            </div>
          </header>

          <div className="hud-canvas">
            <ModuleGrid
              modules={modules}
              placementMode={placementMode}
              onModuleCreate={handleModuleCreate}
              onCancelPlacement={() => setPlacementMode(false)}
              onModuleDelete={handleModuleDelete}
            />
            <div className="hud-caption">
              status: idle <span>// waiting for input</span>
            </div>
          </div>

          <footer className="hud-footer">
            <div className="hud-footer-block">
              <div className="hud-label">CORE</div>
              <div className="hud-value">v0.2.1-alpha</div>
            </div>
            <div className="hud-footer-block">
              <div className="hud-label">UPTIME</div>
              <div className="hud-value">04:12:88</div>
            </div>
          </footer>
        </div>
      </div>
    </GridProvider>
  );
};

export default App;
