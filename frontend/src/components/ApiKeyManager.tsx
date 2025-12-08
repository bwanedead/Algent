import { FormEvent, useState } from "react";
import { ProviderId, saveApiKey } from "../client/backendClient";

const PROVIDERS: { id: ProviderId; label: string }[] = [
  { id: "openai", label: "OpenAI" },
  { id: "anthropic", label: "Anthropic" },
  { id: "gemini", label: "Google Gemini" },
  { id: "xai", label: "xAI / Grok" },
];

const ApiKeyManager = () => {
  const [provider, setProvider] = useState<ProviderId>("openai");
  const [apiKey, setApiKey] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!apiKey.trim()) {
      setError("API key required");
      setStatus(null);
      return;
    }
    setIsSaving(true);
    setError(null);
    setStatus(null);
    const result = await saveApiKey(provider, apiKey.trim());
    setIsSaving(false);
    if (result.status === "ok") {
      setStatus(result.message || "Saved");
      setApiKey("");
    } else {
      setError(
        typeof result.message === "string"
          ? result.message
          : "Unable to save key",
      );
    }
  };

  return (
    <div className="panel" style={{ marginTop: 12 }}>
      <div className="section-title">Model API Keys</div>
      <p style={{ marginTop: 0, color: "#94a3b8" }}>
        Keys are stored via keyring when available. Paste a new key anytime to
        update it.
      </p>
      <form onSubmit={handleSubmit} style={{ display: "flex", gap: 8 }}>
        <select
          value={provider}
          onChange={(e) => setProvider(e.target.value as ProviderId)}
          style={{
            background: "#0b1222",
            color: "#e2e8f0",
            borderRadius: 8,
            border: "1px solid rgba(255,255,255,0.08)",
            padding: "10px 12px",
            minWidth: 160,
          }}
        >
          {PROVIDERS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
        <input
          type="password"
          className="terminal-input"
          placeholder="Paste API key..."
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
        />
        <button
          type="submit"
          disabled={isSaving}
          style={{
            background: "#10b981",
            color: "#0f172a",
            border: "none",
            borderRadius: 8,
            padding: "10px 16px",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          {isSaving ? "Saving..." : "Save"}
        </button>
      </form>
      {status && (
        <div style={{ color: "#34d399", marginTop: 8, fontSize: "0.9rem" }}>
          {status}
        </div>
      )}
      {error && (
        <div style={{ color: "#f87171", marginTop: 8, fontSize: "0.9rem" }}>
          {error}
        </div>
      )}
    </div>
  );
};

export default ApiKeyManager;
