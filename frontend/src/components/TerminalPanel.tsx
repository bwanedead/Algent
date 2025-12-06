import { FormEvent, useEffect, useState } from "react";
import { fetchHealth, sendCommand } from "../client/backendClient";

type LogEntry = {
  label: string;
  payload: unknown;
};

const TerminalPanel = () => {
  const [input, setInput] = useState("help");
  const [log, setLog] = useState<LogEntry[]>([]);

  useEffect(() => {
    fetchHealth().then((payload) =>
      setLog((entries) => [...entries, { label: "health", payload }]),
    );
  }, []);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed) return;

    // TODO: introduce a real parser; for now use the entire line as the command name.
    const response = await sendCommand({
      name: trimmed,
      source: "ui",
    });

    setLog((entries) => [
      ...entries,
      { label: `> ${trimmed}`, payload: response },
    ]);
    setInput("");
  };

  return (
    <div>
      <div className="terminal-log">
        {log.map((entry, idx) => (
          <div key={idx} style={{ marginBottom: 6 }}>
            <div style={{ color: "#a5b4fc" }}>{entry.label}</div>
            <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
              {JSON.stringify(entry.payload, null, 2)}
            </pre>
          </div>
        ))}
      </div>
      <form onSubmit={handleSubmit} style={{ marginTop: 10 }}>
        <input
          className="terminal-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a command (e.g., 'list algorithms')"
          spellCheck={false}
        />
      </form>
    </div>
  );
};

export default TerminalPanel;
