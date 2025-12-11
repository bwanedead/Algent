import { useState } from "react";
import ApiKeyManager from "./components/ApiKeyManager";

const App = () => {
  const [isApiModalOpen, setApiModalOpen] = useState(false);

  const openModal = () => setApiModalOpen(true);
  const closeModal = () => setApiModalOpen(false);

  const handleMouseMove = (e: React.MouseEvent) => {
    const el = e.currentTarget as HTMLElement;
    el.style.setProperty("--cursor-x", `${e.clientX}px`);
    el.style.setProperty("--cursor-y", `${e.clientY}px`);
  };

  return (
    <div className="hud-shell" onMouseMove={handleMouseMove}>
      <div className="hud-noise" aria-hidden="true" />
      <div className="hud-scanlines" aria-hidden="true" />
      
      {/* Global Snap Grid Layers */}
      <div className="hud-grid-layer base-grid" aria-hidden="true" />
      <div className="hud-grid-layer meta-grid" aria-hidden="true" />

      <div className="hud-frame">
        <header className="hud-header">
          <div className="hud-title-block">
            <div className="hud-label">sys.id: 0x9281</div>
            <div className="hud-title">ALGENT::CTRL</div>
          </div>
          <div className="hud-status-block">
            <div className="hud-label">NET</div>
            <div className="hud-value hud-value--online">ACTIVE</div>
          </div>
        </header>
        
        <div className="hud-canvas">
          {/* Canvas content goes here (e.g., workspace, terminals) */}
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

      <button className="api-key-button" onClick={openModal}>
        <span className="button-label">SYSTEM</span>
        <span className="button-text">ACCESS KEYS</span>
      </button>

      {isApiModalOpen && (
        <div className="modal-backdrop" onClick={closeModal}>
          <div
            className="modal-panel"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <div className="modal-eyebrow">credentials</div>
                <h2>model api keys</h2>
              </div>
              <button
                className="icon-button"
                aria-label="Close"
                onClick={closeModal}
              >
                &times;
              </button>
            </div>
            <ApiKeyManager />
          </div>
        </div>
      )}
    </div>
  );
};

export default App;
