import { useState } from "react";
import ApiKeyManager from "./ApiKeyManager";

const SettingsTray = () => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className={`settings-tray ${isOpen ? "open" : ""}`}>
      {/* Expandable Panel */}
      <div className="tray-panel">
        <div className="tray-content">
          <header className="tray-header">
            <h2 className="tray-title">SYS.CONFIG</h2>
          </header>

          <section>
            <div style={{ 
              fontSize: "0.7rem", 
              color: "var(--c-text-dim)", 
              marginBottom: "12px",
              textTransform: "uppercase",
              letterSpacing: "0.1em"
            }}>
              // Access Credentials
            </div>
            <ApiKeyManager />
          </section>

          {/* Future settings can go here */}
        </div>
      </div>

      {/* Toggle Button (Arrow Box) */}
      <button 
        className="tray-toggle" 
        onClick={() => setIsOpen(!isOpen)}
        aria-label={isOpen ? "Close Settings" : "Open Settings"}
      >
        {isOpen ? "←" : "→"}
      </button>
    </div>
  );
};

export default SettingsTray;

