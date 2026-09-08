import React, { useState } from "react";
import { exportProjectAsZip, exportProjectToLocalFolder } from "../lib/exportProject.js";

// Feature 5: Download generated projects as zip or local export.
export default function ExportPanel({ projectName, files, readme }) {
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const hasFiles = files && files.length > 0;

  async function handleZip() {
    setError(null);
    setBusy(true);
    try {
      await exportProjectAsZip(projectName, files);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  async function handleLocalExport() {
    setError(null);
    setBusy(true);
    try {
      await exportProjectToLocalFolder(files);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  if (!hasFiles) return null;

  return (
    <div style={{ marginTop: 20, borderTop: "1px solid var(--border)", paddingTop: 14 }}>
      <div className="panel-title">Export</div>
      {error && <div className="error-banner">{error}</div>}
      <div className="export-row">
        <button className="primary" disabled={busy} onClick={handleZip}>
          Download .zip
        </button>
        <button disabled={busy} onClick={handleLocalExport}>
          Export to folder
        </button>
      </div>
      <div style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 8, lineHeight: 1.5 }}>
        {files.length} files ready ({projectName}). "Export to folder" uses the
        File System Access API (Chromium browsers only); the zip download
        works everywhere.
      </div>
    </div>
  );
}
