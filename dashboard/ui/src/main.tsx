import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { HomePage } from "./pages/HomePage";
import { PipelinePage } from "./pages/PipelinePage";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/pipeline/:pipelineId" element={<PipelinePage />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
