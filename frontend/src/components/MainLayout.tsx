import type { ReactNode } from "react";

type MainLayoutProps = {
  title: string;
  terminalSlot: ReactNode;
  visualizationSlot: ReactNode;
  metricsSlot: ReactNode;
  apiKeyManagerSlot?: ReactNode;
};

const MainLayout = ({
  title,
  terminalSlot,
  visualizationSlot,
  metricsSlot,
  apiKeyManagerSlot,
}: MainLayoutProps) => {
  return (
    <div className="app-shell">
      <header className="panel">
        <div className="section-title">Lab Shell</div>
        <h1 style={{ margin: 0 }}>{title}</h1>
        <p style={{ marginTop: 6, color: "#94a3b8" }}>
          Command-first playground for exploring algorithm behaviors.
        </p>
      </header>
      {apiKeyManagerSlot}

      <main className="grid">
        <section className="panel">
          <div className="section-title">World / Visualization</div>
          {visualizationSlot}
        </section>
        <section className="panel">
          <div className="section-title">Metrics</div>
          {metricsSlot}
        </section>
      </main>

      <section className="panel">
        <div className="section-title">Terminal</div>
        {terminalSlot}
      </section>

      <footer className="footer">
        <span>Backend: localhost:43145 (machine-local)</span>
        <span className="badge">Command-centric</span>
      </footer>
    </div>
  );
};

export default MainLayout;
