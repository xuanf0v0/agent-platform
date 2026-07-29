import type { CopyWorkflowState, CopyWorkflowView, OptimizeContext, WorkflowResult } from "./types";

export async function optimizeListing(
  sourceText: string,
  context: OptimizeContext,
): Promise<WorkflowResult> {
  const response = await fetch("/api/optimize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_text: sourceText, context }),
  });
  const payload = (await response.json()) as WorkflowResult & { message?: string };
  if (!response.ok) {
    throw new Error(payload.message || "优化请求失败");
  }
  return payload;
}

export async function advanceCopyWorkflow(
  state: CopyWorkflowState,
  values: Record<string, string>,
  approved?: boolean,
): Promise<CopyWorkflowView> {
  const response = await fetch("/api/copy-workflow", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ state, values, approved }),
  });
  const payload = await response.json() as CopyWorkflowView & { message?: string };
  if (!response.ok) throw new Error(payload.message || "工作流请求失败");
  return payload;
}
