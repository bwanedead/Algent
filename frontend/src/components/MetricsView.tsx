const MetricsView = () => {
  const placeholderMetrics = [
    { name: "iteration", value: "N/A" },
    { name: "speed", value: "N/A" },
    { name: "custom", value: "N/A" },
  ];

  return (
    <div className="metrics-grid">
      {placeholderMetrics.map((metric) => (
        <div key={metric.name} className="metric-card">
          <div className="section-title">{metric.name}</div>
          <div style={{ fontSize: "1.25rem" }}>{metric.value}</div>
          <div style={{ marginTop: 6, color: "#94a3b8" }}>
            TODO: live updates from backend
          </div>
        </div>
      ))}
    </div>
  );
};

export default MetricsView;
