import type { CreationSession } from "./types";

export async function sendTurn(message: string, session: CreationSession | null): Promise<CreationSession> {
  const response = await fetch("/api/session/turn", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message, session }) });
  const payload = await response.json() as CreationSession & { message?: string };
  if (!response.ok) throw new Error(payload.message || "创作请求失败");
  return payload;
}

export async function uploadImages(sessionId: string, files: File[]): Promise<number> {
  const images = await Promise.all(files.slice(0, 8).map(async (file) => ({
    name: file.name,
    data_url: await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(reader.error || new Error("图片读取失败"));
      reader.readAsDataURL(file);
    }),
  })));
  const response = await fetch("/api/session/images", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, images }),
  });
  const payload = await response.json() as { count?: number; message?: string };
  if (!response.ok) throw new Error(payload.message || "图片上传失败");
  return payload.count || 0;
}
