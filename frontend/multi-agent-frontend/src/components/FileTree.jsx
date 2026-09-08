import React, { useState } from "react";
import { buildFileTree } from "../lib/schemas.js";

function TreeNode({ node, depth, selectedPath, onSelect }) {
  const [expanded, setExpanded] = useState(true);

  if (node.type === "file") {
    return (
      <div
        className={"tree-node-row" + (selectedPath === node.path ? " selected" : "")}
        style={{ paddingLeft: depth * 10 }}
        onClick={() => onSelect(node.file)}
      >
        <span>📄</span>
        <span>{node.name}</span>
      </div>
    );
  }

  const childEntries = Object.values(node.children).sort((a, b) => {
    if (a.type !== b.type) return a.type === "dir" ? -1 : 1;
    return a.name.localeCompare(b.name);
  });

  return (
    <div className="tree-node">
      {node.name && (
        <div
          className="tree-node-row"
          style={{ paddingLeft: depth * 10 }}
          onClick={() => setExpanded((e) => !e)}
        >
          <span>{expanded ? "📂" : "📁"}</span>
          <span>{node.name}</span>
        </div>
      )}
      {expanded && (
        <div className="tree-children">
          {childEntries.map((child) => (
            <TreeNode
              key={child.name}
              node={child}
              depth={node.name ? depth + 1 : depth}
              selectedPath={selectedPath}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// Feature 3 (part A): interactive file tree explorer.
export default function FileTree({ files, selectedPath, onSelect }) {
  if (!files || files.length === 0) {
    return <div style={{ fontSize: 12.5, color: "var(--text-dim)" }}>No files generated yet.</div>;
  }
  const tree = buildFileTree(files);
  return (
    <div className="file-tree">
      <TreeNode node={tree} depth={0} selectedPath={selectedPath} onSelect={onSelect} />
    </div>
  );
}
