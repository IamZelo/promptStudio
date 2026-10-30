// Thin client for the FastAPI wrapper around backend/src/pipeline.py.
// Expects a backend route like:
//
//   POST /api/generate  (body: { prompt, mock })
//   -> text/event-stream, each event: `data: {"type": ..., ...}\n\n`
//
// Falls back to the local mock stream (src/mocks/mockPipelineStream.js) when
// VITE_FORCE_MOCK=1 or when the real backend is unreachable, so the UI is
// always demoable offline.

import { runMockPipeline } from "../mocks/mockPipelineStream.js";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const FORCE_MOCK = import.meta.env.VITE_FORCE_MOCK === "1";

// Runs the pipeline (real or mock) and invokes onEvent for every SSE-style
// event. Returns an object with an abort() method to cancel the stream.
export function startPipeline(prompt, { mock = false, onEvent }) {
  const controller = new AbortController();

  async function run() {
    if (FORCE_MOCK || mock) {
      await runMockPipeline(prompt, onEvent, { signal: controller.signal });
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/api/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, mock }),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        throw new Error(`Backend responded with ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE frames are separated by a blank line; parse only complete frames.
        const frames = buffer.split("\n\n");
        buffer = frames.pop(); // keep any incomplete trailing frame in buffer

        for (const frame of frames) {
          const line = frame.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          const jsonStr = line.slice(5).trim();
          try {
            onEvent(JSON.parse(jsonStr));
          } catch {
            // Ignore malformed/partial frame; real backend should send valid JSON per event.
          }
        }
      }
    } catch (err) {
      if (err.name === "AbortError") return;
      // Backend unreachable or errored: transparently fall back to the mock
      // stream so the UI remains usable during frontend-only development.
      onEvent({ type: "agent_status", agent: "system", status: "backend_unreachable" });
      await runMockPipeline(prompt, onEvent, { signal: controller.signal });
    }
  }

  run();
  return { abort: () => controller.abort() };
}

// Fetches the list of prompt templates. Falls back to a static local list.
export async function fetchTemplates() {
  try {
    const res = await fetch(`${API_BASE}/api/templates`);
    if (!res.ok) throw new Error("no templates endpoint");
    return await res.json();
  } catch {
    return [
      { id: "cli-notes", label: "Markdown Note CLI", prompt: "Build a markdown note-taking CLI tool" },
      { id: "pomodoro", label: "Pomodoro Timer", prompt: "Create a CLI Pomodoro timer with task tracking" },
      { id: "todo-api", label: "Todo REST API", prompt: "Build a FastAPI todo list REST API with SQLite persistence" },
      { id: "web-scraper", label: "Web Scraper", prompt: "Build a Python web scraper that exports results to CSV" },
    ];
  }
}
