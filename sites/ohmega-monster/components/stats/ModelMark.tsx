import "./stats.css";

// The small "model-assessed" mark: a language model's reading or extraction, not a measurement (lib/stats/registry.ts basis "model").

export function ModelMark() {
  return (
    <span className="stat-model" title="Model-assessed: a language model's reading, not a measurement">
      model-assessed
    </span>
  );
}
