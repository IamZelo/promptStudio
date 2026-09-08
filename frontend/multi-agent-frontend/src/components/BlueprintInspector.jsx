import React from "react";

// Feature 3 (part B): interactive blueprint inspector.
// Renders the Architect Agent's ArchitectureBlueprint (schemas.py contract):
// { project_name, summary, files: FileSpec[], requirements: string[] }
export default function BlueprintInspector({ blueprint, selectedPath, onSelectFile }) {
  if (!blueprint || !blueprint.project_name) {
    return (
      <div style={{ fontSize: 12.5, color: "var(--text-dim)" }}>
        Blueprint will appear here once the Architect Agent finishes planning.
      </div>
    );
  }

  return (
    <div>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>{blueprint.project_name}</div>
      <div className="blueprint-summary">{blueprint.summary}</div>

      <div className="panel-title" style={{ marginTop: 16 }}>Planned Files</div>
      <div style={{ fontSize: 12.5, marginBottom: 16 }}>
        {blueprint.files.map((f) => (
          <div
            key={f.path}
            onClick={() => onSelectFile({ path: f.path, language: f.language })}
            style={{
              padding: "5px 0",
              borderBottom: "1px solid var(--border)",
              cursor: "pointer",
              color: selectedPath === f.path ? "var(--accent)" : "var(--text)",
            }}
          >
            <div style={{ fontFamily: "monospace" }}>{f.path}</div>
            <div style={{ color: "var(--text-dim)", fontSize: 11.5 }}>{f.description}</div>
          </div>
        ))}
      </div>

      <div className="panel-title">requirements.txt</div>
      <ul className="req-list">
        {blueprint.requirements.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
    </div>
  );
}
