import React, { useCallback, useRef, useState } from "react";
import PromptPanel from "./components/PromptPanel.jsx";
import AgentStreamPanel from "./components/AgentStreamPanel.jsx";
import BlueprintInspector from "./components/BlueprintInspector.jsx";
import FileTree from "./components/FileTree.jsx";
import CodePreview from "./components/CodePreview.jsx";
import ExportPanel from "./components/ExportPanel.jsx";
import { startPipeline } from "./lib/apiClient.js";
import { emptyBlueprint } from "./lib/schemas.js";

const TABS = { STREAM: "stream", BLUEPRINT: "blueprint" };

export default function App() {
  const [isRunning, setIsRunning] = useState(false);
  const [useMock, setUseMock] = useState(true);
  const [activeTab, setActiveTab] = useState(TABS.STREAM);

  const [agentLogs, setAgentLogs] = useState([]);
  const [agentStatus, setAgentStatus] = useState({});
  const [blueprint, setBlueprint] = useState(emptyBlueprint());
  const [generatedFiles, setGeneratedFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [readme, setReadme] = useState("");
  const [errorMsg, setErrorMsg] = useState(null);

  const pipelineRef = useRef(null);

  const handleEvent = useCallback((evt) => {
    switch (evt.type) {
      case "agent_status":
        setAgentStatus((prev) => ({ ...prev, [evt.agent]: evt.status }));
        break;
      case "agent_chunk":
        setAgentLogs((prev) => [...prev, { agent: evt.agent, chunk: evt.chunk }]);
        break;
      case "blueprint":
        setBlueprint(evt.blueprint);
        setActiveTab(TABS.BLUEPRINT);
        break;
      case "file_done":
        setGeneratedFiles((prev) => {
          const next = prev.filter((f) => f.path !== evt.file.path);
          return [...next, evt.file];
        });
        setSelectedFile((cur) => cur || evt.file);
        break;
      case "pipeline_done":
        setReadme(evt.readme);
        setIsRunning(false);
        break;
      case "error":
        setErrorMsg(evt.message);
        setIsRunning(false);
        break;
      default:
        break;
    }
  }, []);

  function handleSubmit(prompt) {
    setAgentLogs([]);
    setAgentStatus({});
    setBlueprint(emptyBlueprint());
    setGeneratedFiles([]);
    setSelectedFile(null);
    setReadme("");
    setErrorMsg(null);
    setActiveTab(TABS.STREAM);
    setIsRunning(true);

    pipelineRef.current = startPipeline(prompt, { mock: useMock, onEvent: handleEvent });
  }

  function handleCancel() {
    pipelineRef.current?.abort();
    setIsRunning(false);
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-title">
          Multi-Agent Coding Orchestrator <span>Architect + Developer pipeline</span>
        </div>
        {isRunning && <button onClick={handleCancel}>Cancel run</button>}
      </header>

      <div className="app-body">
        <div className="panel">
          <PromptPanel
            onSubmit={handleSubmit}
            isRunning={isRunning}
            useMock={useMock}
            setUseMock={setUseMock}
          />
          {errorMsg && <div className="error-banner">{errorMsg}</div>}

          <div className="panel-title" style={{ marginTop: 20 }}>File Explorer</div>
          <FileTree
            files={generatedFiles}
            selectedPath={selectedFile?.path}
            onSelect={setSelectedFile}
          />

          <ExportPanel
            projectName={blueprint.project_name}
            files={generatedFiles}
            readme={readme}
          />
        </div>

        <div className="center-column">
          <div className="tabs">
            <div
              className={"tab" + (activeTab === TABS.STREAM ? " active" : "")}
              onClick={() => setActiveTab(TABS.STREAM)}
            >
              Agent Stream
            </div>
            <div
              className={"tab" + (activeTab === TABS.BLUEPRINT ? " active" : "")}
              onClick={() => setActiveTab(TABS.BLUEPRINT)}
            >
              Blueprint
            </div>
          </div>
          <div className="tab-content">
            {activeTab === TABS.STREAM ? (
              <AgentStreamPanel agentLogs={agentLogs} agentStatus={agentStatus} />
            ) : (
              <div style={{ padding: 14, overflowY: "auto" }}>
                <BlueprintInspector
                  blueprint={blueprint}
                  selectedPath={selectedFile?.path}
                  onSelectFile={setSelectedFile}
                />
              </div>
            )}
          </div>
        </div>

        <div className="panel" style={{ padding: 0 }}>
          <CodePreview file={selectedFile} />
        </div>
      </div>
    </div>
  );
}
