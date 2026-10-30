import React, { useEffect, useRef } from "react";

// Feature 2: Live streaming display of Architect and Developer agent outputs.
export default function AgentStreamPanel({ agentLogs, agentStatus }) {
  const logRef = useRef(null);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [agentLogs]);

  const agents = ["architect", "developer"];

  if (agentLogs.length === 0) {
    return (
      <div className="empty-state">
        No pipeline run yet. Enter a prompt on the left and click{" "}
        <strong>Generate Project</strong> to watch the Architect and Developer
        agents stream their reasoning here in real time.
      </div>
    );
  }

  return (
    <div className="agent-log" ref={logRef}>
      {agents.map((agent) => {
        const chunks = agentLogs.filter((l) => l.agent === agent);
        if (chunks.length === 0) return null;
        const status = agentStatus[agent] || "idle";
        return (
          <div key={agent} className={`agent-block agent-${agent}`}>
            <div className="agent-label">
              <span className={`status-dot ${status}`} />
              {agent === "architect" ? "Architect Agent" : "Developer Agent"}
              <span style={{ color: "var(--text-dim)", fontWeight: 400, fontSize: 11 }}>
                {status === "started" ? "streaming..." : status === "done" ? "complete" : ""}
              </span>
            </div>
            <div className="agent-chunk-text">
              {chunks.map((c) => c.chunk).join("")}
            </div>
          </div>
        );
      })}
    </div>
  );
}
