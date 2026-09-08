import React, { useEffect, useState } from "react";
import { fetchTemplates } from "../lib/apiClient.js";

// Feature 1: Visual prompt input and template selector.
export default function PromptPanel({ onSubmit, isRunning, useMock, setUseMock }) {
  const [templates, setTemplates] = useState([]);
  const [prompt, setPrompt] = useState("");
  const [activeTemplateId, setActiveTemplateId] = useState(null);

  useEffect(() => {
    fetchTemplates().then(setTemplates);
  }, []);

  function applyTemplate(t) {
    setPrompt(t.prompt);
    setActiveTemplateId(t.id);
  }

  function handleSubmit(e) {
    e.preventDefault();
    if (!prompt.trim() || isRunning) return;
    onSubmit(prompt.trim());
  }

  return (
    <div>
      <div className="panel-title">New Project</div>
      <form className="prompt-form" onSubmit={handleSubmit}>
        <textarea
          rows={5}
          placeholder='Describe what to build, e.g. "Build a CLI Pomodoro timer with task tracking"'
          value={prompt}
          onChange={(e) => {
            setPrompt(e.target.value);
            setActiveTemplateId(null);
          }}
        />

        <div className="template-select">
          <span style={{ fontSize: 12, color: "var(--text-dim)" }}>Templates</span>
          <div className="template-chip-row">
            {templates.map((t) => (
              <button
                key={t.id}
                type="button"
                className={"template-chip" + (activeTemplateId === t.id ? " active" : "")}
                onClick={() => applyTemplate(t)}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "var(--text-dim)" }}>
          <input
            type="checkbox"
            checked={useMock}
            onChange={(e) => setUseMock(e.target.checked)}
            style={{ width: "auto" }}
          />
          Run in --mock mode (offline, no API key)
        </label>

        <button type="submit" className="primary" disabled={isRunning || !prompt.trim()}>
          {isRunning ? "Running pipeline..." : "Generate Project"}
        </button>
      </form>
    </div>
  );
}
