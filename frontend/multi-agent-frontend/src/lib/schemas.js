// Mirrors backend/src/schemas.py (Pydantic models) so the frontend and
// backend agree on shape. Keep this in sync whenever schemas.py changes.
//
// FileSpec        -> { path: string, description: string, language?: string }
// ArchitectureBlueprint -> {
//   project_name: string,
//   summary: string,
//   files: FileSpec[],
//   requirements: string[]   // always includes requirements.txt entries
// }
// GeneratedFile   -> { path: string, content: string, language?: string }
// PipelineResult  -> {
//   blueprint: ArchitectureBlueprint,
//   generated_files: GeneratedFile[],
//   readme: string
// }

export function emptyBlueprint() {
  return { project_name: "", summary: "", files: [], requirements: [] };
}

// Best-effort language detection for Monaco, based on file extension.
export function languageFromPath(path = "") {
  const ext = path.split(".").pop().toLowerCase();
  const map = {
    py: "python",
    js: "javascript",
    jsx: "javascript",
    ts: "typescript",
    tsx: "typescript",
    json: "json",
    md: "markdown",
    txt: "plaintext",
    yml: "yaml",
    yaml: "yaml",
    toml: "ini",
    html: "html",
    css: "css",
    sh: "shell",
    env: "ini",
  };
  return map[ext] || "plaintext";
}

// Builds a nested tree structure from a flat list of { path } objects,
// e.g. "src/agents/architect.py" -> src / agents / architect.py
export function buildFileTree(fileList) {
  const root = { name: "", type: "dir", children: {} };
  for (const f of fileList) {
    const parts = f.path.split("/").filter(Boolean);
    let node = root;
    parts.forEach((part, i) => {
      const isLeaf = i === parts.length - 1;
      if (!node.children[part]) {
        node.children[part] = isLeaf
          ? { name: part, type: "file", path: f.path, file: f }
          : { name: part, type: "dir", children: {} };
      }
      node = node.children[part];
    });
  }
  return root;
}
