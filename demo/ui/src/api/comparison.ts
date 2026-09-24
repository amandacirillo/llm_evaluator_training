import axios from "axios";
import type { ModelsResponse, RunResult, StreamedOutput } from "../types";

export async function fetchModels(): Promise<ModelsResponse> {
  const { data } = await axios.get<ModelsResponse>("/api/models");
  return data;
}

export interface RunRequest {
  prompt: string;
  title?: string;
  models: string[];
}

export interface RunHandlers {
  onOutputs?: (outputs: StreamedOutput[]) => void;
  onScoring?: () => void;
  onDone?: (result: RunResult) => void;
  onError?: (message: string) => void;
}

/** Scoring mode — auto-generate the checklist and grade it (SSE). No review step. */
export function score(req: RunRequest, handlers: RunHandlers): Promise<void> {
  return postSSE("/api/score", req, handlers);
}

/** Output-only mode — compare outputs side by side (SSE). */
export function generateOutputs(req: RunRequest, handlers: RunHandlers): Promise<void> {
  return postSSE("/api/generate", req, handlers);
}

/**
 * POST a request and parse the Server-Sent Events stream, dispatching each event
 * to the matching handler. Uses fetch + ReadableStream (not axios) so staged
 * progress arrives incrementally.
 */
async function postSSE(url: string, body: unknown, handlers: RunHandlers): Promise<void> {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!resp.ok || !resp.body) {
    let message = `Request failed (${resp.status})`;
    try {
      const errBody = await resp.json();
      if (errBody?.error) message = errBody.error;
    } catch {
      /* ignore non-JSON error bodies */
    }
    handlers.onError?.(message);
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatch = (eventName: string, dataStr: string) => {
    let data: unknown;
    try {
      data = JSON.parse(dataStr);
    } catch {
      return;
    }
    const d = data as Record<string, unknown>;
    switch (eventName) {
      case "outputs":
        handlers.onOutputs?.(d.outputs as StreamedOutput[]);
        break;
      case "scoring":
        handlers.onScoring?.();
        break;
      case "done":
        handlers.onDone?.(data as RunResult);
        break;
      case "error":
        handlers.onError?.(String(d.error ?? "Unknown error"));
        break;
    }
  };

  const flushFrame = (frame: string) => {
    const lines = frame.split("\n");
    let eventName = "message";
    const dataLines: string[] = [];
    for (const line of lines) {
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (dataLines.length) dispatch(eventName, dataLines.join("\n"));
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      if (frame.trim()) flushFrame(frame);
    }
  }
  if (buffer.trim()) flushFrame(buffer);
}
