import type { OptimizeContext, WorkflowResult } from "./types";

export async function optimizeListing(sourceText: string, context: OptimizeContext): Promise<WorkflowResult> {
  const response = await fetch("/api/optimize", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_text: sourceText, context }),
  });
  const payload = await response.json() as WorkflowResult & { message?: string };
  if (!response.ok) throw new Error(payload.message || "优化请求失败");
  return payload;
}
