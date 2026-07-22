import { getJson, postJson } from "./http.js";

export const interviewsApi = {
  options: () => getJson("/interview-options"),
  readiness: () => getJson("/health/ready"),
  create: (body, idempotencyKey) => postJson("/interviews", body, { idempotencyKey }),
  history: ({ page = 1, pageSize = 10 } = {}) => {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    return getJson(`/interviews?${query}`);
  },
  snapshot: (interviewId) => getJson(`/interviews/${interviewId}`),
  report: (interviewId) => getJson(`/interviews/${interviewId}/report`)
};
