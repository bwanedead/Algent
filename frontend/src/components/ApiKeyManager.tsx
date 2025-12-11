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
    <div className="api-key-manager">
      <p className="api-key-helper">
        Keys are stored securely via the backend keyring (when available). Paste
        new credentials anytime to update them.
      </p>
      <form className="api-key-form" onSubmit={handleSubmit}>
        <label className="api-key-field">
          <span>Provider</span>
          <select
            className="api-key-select"
            value={provider}
            onChange={(e) => setProvider(e.target.value as ProviderId)}
          >
            {PROVIDERS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        <label className="api-key-field">
          <span>API Key</span>
          <input
            type="password"
            className="api-key-input"
            placeholder="Paste provider key..."
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </label>
        <div className="api-key-actions">
          <button type="submit" disabled={isSaving}>
            {isSaving ? "Saving..." : "Save Key"}
          </button>
        </div>
      </form>
      {status && <div className="status-message">{status}</div>}
      {error && <div className="status-error">{error}</div>}
    </div>
  );
};

export default ApiKeyManager;
