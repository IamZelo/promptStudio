import React from "react";
import Editor from "@monaco-editor/react";
import { languageFromPath } from "../lib/schemas.js";

// Feature 4: In-browser code preview with syntax highlighting (Monaco Editor,
// the same engine that powers VS Code -- supports Python, JS/TS, JSON,
// Markdown, YAML, etc. out of the box).
export default function CodePreview({ file }) {
  if (!file) {
    return (
      <div className="empty-state">
        Select a file from the tree or blueprint to preview its generated
        code here.
      </div>
    );
  }

  const language = file.language || languageFromPath(file.path);

  return (
    <div className="tab-content">
      <div className="editor-toolbar">
        <span className="editor-path">{file.path}</span>
        <span style={{ color: "var(--text-dim)" }}>{language}</span>
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        <Editor
          height="100%"
          language={language}
          value={file.content || "// Content will appear once the Developer Agent writes this file."}
          theme="vs-dark"
          options={{
            readOnly: true,
            minimap: { enabled: false },
            fontSize: 13,
            scrollBeyondLastLine: false,
            wordWrap: "on",
          }}
        />
      </div>
    </div>
  );
}
