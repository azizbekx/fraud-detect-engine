import type { Anchor, CaseSummary, ChatAnswer, Finding, Source, Trace } from "./types";

const json = async <T>(response: Response): Promise<T> => {
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail || "Request failed");
  }
  return response.json() as Promise<T>;
};

export const api = {
  cases: () => fetch("/api/cases").then((r) => json<CaseSummary[]>(r)),
  createSample: () => fetch("/api/cases/sample", { method: "POST" }).then((r) => json<CaseSummary>(r)),
  upload: (file: File, name: string) => {
    const body = new FormData();
    body.append("name", name);
    body.append("files", file);
    return fetch("/api/cases", { method: "POST", body }).then((r) => json<CaseSummary>(r));
  },
  case: (id: string) => fetch(`/api/cases/${id}`).then((r) => json<CaseSummary>(r)),
  sources: (id: string) => fetch(`/api/cases/${id}/sources`).then((r) => json<Source[]>(r)),
  findings: (id: string) => fetch(`/api/cases/${id}/findings?include_cleared=true`).then((r) => json<Finding[]>(r)),
  trace: (id: string) => fetch(`/api/findings/${id}/trace`).then((r) => json<Trace>(r)),
  anchor: (id: string) => fetch(`/api/anchors/${id}`).then((r) => json<{ anchor: Anchor; source: Source }>(r)),
  review: (id: string, state: string, note = "") =>
    fetch(`/api/findings/${id}/review`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ state, note }),
    }).then((r) => json<Finding>(r)),
  ask: (caseId: string, question: string) =>
    fetch(`/api/cases/${caseId}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    }).then((r) => json<ChatAnswer>(r)),
};
