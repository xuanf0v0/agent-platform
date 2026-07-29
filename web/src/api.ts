import type { CreationSession } from "./types";

export async function sendTurn(message: string, session: CreationSession | null): Promise<CreationSession> {
  const response = await fetch("/api/session/turn", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message, session, mock: true }) });
  const payload = await response.json() as CreationSession & { message?: string };
  if (!response.ok) throw new Error(payload.message || "创作请求失败");
  return payload;
}
