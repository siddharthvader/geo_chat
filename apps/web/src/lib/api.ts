import type { Building, ChatRequest, ChatResponse, Hotspot } from "@buildingtalk/shared";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const CHAT_TIMEOUT_MS = Number(process.env.NEXT_PUBLIC_CHAT_TIMEOUT_MS || 25000);

export class APIError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = "APIError";
    this.status = status;
  }
}

export async function fetchBuildings(): Promise<Building[]> {
  const res = await fetch(`${API_BASE}/buildings`, { cache: "no-store" });
  if (!res.ok) {
    throw new APIError(`Failed to fetch buildings`, res.status);
  }
  return (await res.json()) as Building[];
}

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`, { cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
}

export async function fetchHotspots(buildingId?: string): Promise<Hotspot[]> {
  const url = buildingId ? `${API_BASE}/hotspots?building_id=${encodeURIComponent(buildingId)}` : `${API_BASE}/hotspots`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new APIError(`Failed to fetch hotspots`, res.status);
  }
  return (await res.json()) as Hotspot[];
}

export async function sendChat(body: ChatRequest): Promise<ChatResponse> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new APIError(`Chat timed out after ${Math.round(CHAT_TIMEOUT_MS / 1000)}s`);
    }
    throw new APIError("Could not reach API. Check network or backend status.");
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) {
    throw new APIError("Failed to chat", res.status);
  }
  return (await res.json()) as ChatResponse;
}
