// Feature 5: Download generated projects as zip or local export.
import JSZip from "jszip";
import { saveAs } from "file-saver";

export async function exportProjectAsZip(projectName, files) {
  const zip = new JSZip();
  for (const file of files) {
    zip.file(file.path, file.content);
  }
  const blob = await zip.generateAsync({ type: "blob" });
  saveAs(blob, `${projectName || "generated-project"}.zip`);
}

// "Local export" fallback: writes each file individually via the File System
// Access API when available (Chromium-based browsers), letting the user pick
// a folder on disk instead of downloading a zip.
export async function exportProjectToLocalFolder(files) {
  if (!("showDirectoryPicker" in window)) {
    throw new Error(
      "Local folder export is not supported in this browser. Use the ZIP download instead."
    );
  }
  const dirHandle = await window.showDirectoryPicker();
  for (const file of files) {
    const parts = file.path.split("/").filter(Boolean);
    let handle = dirHandle;
    for (let i = 0; i < parts.length - 1; i++) {
      handle = await handle.getDirectoryHandle(parts[i], { create: true });
    }
    const fileHandle = await handle.getFileHandle(parts[parts.length - 1], { create: true });
    const writable = await fileHandle.createWritable();
    await writable.write(file.content);
    await writable.close();
  }
}
