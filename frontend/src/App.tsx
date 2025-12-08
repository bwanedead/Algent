import MainLayout from "./components/MainLayout";
import ApiKeyManager from "./components/ApiKeyManager";
import MetricsView from "./components/MetricsView";
import TerminalPanel from "./components/TerminalPanel";
import WorldView from "./components/WorldView";

function App() {
  return (
    <MainLayout
      title="Algent Lab"
      terminalSlot={<TerminalPanel />}
      visualizationSlot={<WorldView />}
      metricsSlot={<MetricsView />}
      apiKeyManagerSlot={<ApiKeyManager />}
    />
  );
}

export default App;
