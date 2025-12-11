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
          <div className="metric-label">{metric.name}</div>
          <div className="metric-value">{metric.value}</div>
          <div className="metric-sub">
            TODO: live updates from backend
          </div>
        </div>
      ))}
    </div>
  );
};

export default MetricsView;
