"use client";

import type { Building, ChatRequest, ChatResponse, Citation, Hotspot } from "@buildingtalk/shared";
import BuildingViewer from "@/components/BuildingViewer";
import { APIError, checkHealth, fetchBuildings, fetchHotspots, sendChat } from "@/lib/api";
import { track } from "@/lib/analytics";
import { buildClientContext, getHotspotPrimer, type HotspotPrimer } from "@/lib/hotspotPrimers";
import { useEffect, useMemo, useState } from "react";

type UIMessage = {
  role: "user" | "assistant";
  text: string;
  citations?: Citation[];
  latencyMs?: number;
};

const TRY_THESE_FIVE = [
  "What are the weeping ladies?",
  "Why does this structure look like a ruin?",
  "When was the Palace reconstructed?",
  "What details show classical Corinthian influence?",
  "What is the role of the lagoon axis in the composition?",
];

const HOTSPOT_FLY_CONFIDENCE = 0.78;

function uid(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function formatError(err: unknown): string {
  if (err instanceof APIError) {
    if (err.status === 429) {
      return "The service is rate-limited right now. Please wait a moment and retry.";
    }
    if (err.status && err.status >= 500) {
      return "The backend had an error while generating an answer. Please retry.";
    }
    return err.message;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return "Request failed. Please retry.";
}

export default function HomePage() {
  const [canUseDebug, setCanUseDebug] = useState(false);
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [selectedBuildingId, setSelectedBuildingId] = useState<string>("palace_of_fine_arts");
  const [hotspots, setHotspots] = useState<Hotspot[]>([]);
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [activeHotspotIds, setActiveHotspotIds] = useState<string[]>([]);
  const [activePrimer, setActivePrimer] = useState<HotspotPrimer | null>(null);
  const [viewerModelUrl, setViewerModelUrl] = useState<string>("/models/palace.glb");
  const [modelNotice, setModelNotice] = useState<string>("");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [debugMode, setDebugMode] = useState(false);
  const [error, setError] = useState<string>("");
  const [notice, setNotice] = useState<string>("");
  const [lastQuestion, setLastQuestion] = useState<string>("");

  const sessionId = useMemo(uid, []);

  const selectedBuilding = useMemo(
    () => buildings.find((building) => building.id === selectedBuildingId),
    [buildings, selectedBuildingId],
  );

  const promptsToShow =
    selectedBuilding?.suggestedPrompts && selectedBuilding.suggestedPrompts.length > 0
      ? selectedBuilding.suggestedPrompts.slice(0, 5)
      : TRY_THESE_FIVE;

  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      setCanUseDebug(params.get("debug") === "1");
    }
  }, []);

  useEffect(() => {
    if (!canUseDebug) {
      setDebugMode(false);
    }
  }, [canUseDebug]);

  useEffect(() => {
    track("page_view", { page: "home" });
    checkHealth().then((ok) => {
      if (!ok) {
        setNotice("Backend health check failed. You can still try, but responses may fail until the API is up.");
      }
    });
    fetchBuildings()
      .then((rows) => {
        setBuildings(rows);
        setSelectedBuildingId((current) =>
          rows.find((building) => building.id === current) ? current : (rows[0]?.id ?? current),
        );
      })
      .catch((err: unknown) => {
        setError(formatError(err));
      });
  }, []);

  useEffect(() => {
    if (!selectedBuildingId) {
      return;
    }

    setActiveHotspotIds([]);
    setActivePrimer(null);
    setMessages([]);
    setInput("");
    setError("");

    fetchHotspots(selectedBuildingId)
      .then(setHotspots)
      .catch((err: unknown) => {
        setError(formatError(err));
      });
  }, [selectedBuildingId]);

  useEffect(() => {
    let cancelled = false;
    async function checkModel() {
      if (!selectedBuilding) {
        return;
      }
      setModelNotice("");

      try {
        const response = await fetch(selectedBuilding.modelUrl, { method: "HEAD" });
        if (!cancelled && response.ok) {
          setViewerModelUrl(selectedBuilding.modelUrl);
          return;
        }
      } catch {
        // Fall through to default model.
      }

      if (!cancelled) {
        setViewerModelUrl("/models/palace.glb");
        setModelNotice(
          `Model file not found for ${selectedBuilding.name}. Showing Palace of Fine Arts model as fallback.`,
        );
      }
    }

    checkModel().catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [selectedBuilding]);

  function focusHotspotById(hotspotId: string) {
    setActiveHotspotIds([hotspotId]);
    const hotspot = hotspots.find((h) => h.id === hotspotId);
    if (hotspot) {
      setActivePrimer(getHotspotPrimer(selectedBuildingId, hotspot));
      track("hotspot_focus_manual", { hotspot_id: hotspot.id, building_id: selectedBuildingId });
    }
  }

  async function submitMessage(message: string) {
    const normalized = message.trim();
    if (!normalized || busy) {
      return;
    }

    setBusy(true);
    setError("");
    setNotice("");
    setMessages((prev) => [...prev, { role: "user", text: normalized }]);
    setInput("");
    setLastQuestion(normalized);
    track("chat_submit", { building_id: selectedBuildingId, chars: normalized.length });
    const start = performance.now();

    try {
      const body: ChatRequest = {
        session_id: sessionId,
        message: normalized,
        building_id: selectedBuildingId,
      };
      if (activePrimer) {
        body.client_context = buildClientContext(activePrimer);
      }

      const response: ChatResponse = await sendChat(body);
      const elapsed = Math.round(performance.now() - start);
      const citationCount = response.citations.length;
      const confidentHotspots = response.actions.hotspots.filter((h) => h.confidence >= HOTSPOT_FLY_CONFIDENCE);
      track("chat_success", {
        building_id: selectedBuildingId,
        latency_ms: elapsed,
        citation_count: citationCount,
        hotspot_count: response.actions.hotspots.length,
        confident_hotspot_count: confidentHotspots.length,
      });

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: response.answer,
          citations: response.citations,
          latencyMs: elapsed,
        },
      ]);

      const hotspotIds = confidentHotspots.map((h) => h.id);
      if (hotspotIds.length > 0) {
        setActiveHotspotIds(hotspotIds);
        const topHotspot = hotspots.find((h) => h.id === hotspotIds[0]);
        if (topHotspot) {
          setActivePrimer(getHotspotPrimer(selectedBuildingId, topHotspot));
        }
      } else if (response.actions.hotspots.length > 0) {
        setNotice("Hotspot confidence was below threshold, so camera motion was intentionally skipped.");
      } else {
        setActiveHotspotIds([]);
      }

      if (response.citations.length === 0) {
        setNotice("No grounded citation was available for this answer, so confidence was reduced.");
      }
    } catch (err: unknown) {
      track("chat_error", { building_id: selectedBuildingId });
      setError(formatError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen grid-cols-1 gap-4 p-3 md:p-4 xl:grid-cols-[1.6fr_1fr]">
      <section className="relative flex min-h-[48vh] flex-col overflow-hidden rounded-3xl border border-black/10 bg-white/45 p-3 shadow-panel md:min-h-[60vh]">
        <div className="mb-3 flex items-center justify-between gap-3 rounded-2xl bg-white/70 px-3 py-2">
          <div>
            <h1 className="font-[var(--font-display)] text-xl tracking-tight text-ink">
              {selectedBuilding?.name || "Palace of Fine Arts"}
            </h1>
            <p className="font-[var(--font-body)] text-xs text-ink/75">
              Interactive 3D guide with cited answers and camera focus.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {buildings.length > 1 && (
              <select
                value={selectedBuildingId}
                onChange={(event) => setSelectedBuildingId(event.target.value)}
                className="rounded-md border border-black/20 bg-white px-2 py-1 text-xs"
              >
                {buildings.map((building) => (
                  <option key={building.id} value={building.id}>
                    {building.name}
                  </option>
                ))}
              </select>
            )}
            {canUseDebug && (
              <button
                type="button"
                className="rounded-md border border-black/15 bg-[#f2dfc5] px-3 py-1 text-sm"
                onClick={() => setDebugMode((v) => !v)}
              >
                {debugMode ? "Debug On" : "Debug Off"}
              </button>
            )}
          </div>
        </div>

        {selectedBuilding && (
          <div className="mb-2 rounded-xl bg-white/60 px-3 py-2 text-xs text-ink/80">
            <div className="font-semibold">{selectedBuilding.name}</div>
            <div>
              {selectedBuilding.location} • {selectedBuilding.description}
            </div>
          </div>
        )}

        {modelNotice && <div className="mb-2 rounded-xl bg-[#f7e8cf] px-3 py-2 text-xs text-[#7a4f1b]">{modelNotice}</div>}

        <div className="relative flex-1">
          <BuildingViewer
            hotspots={hotspots}
            activeHotspotIds={activeHotspotIds}
            debugMode={debugMode}
            modelUrl={viewerModelUrl}
          />
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {hotspots.slice(0, 12).map((hotspot) => (
            <button
              key={hotspot.id}
              type="button"
              className={`rounded-full border px-3 py-1 text-xs hover:bg-[#efd8bd] ${
                activeHotspotIds.includes(hotspot.id) ? "border-[#9a3f22] bg-[#f0d2b7]" : "border-black/10 bg-white/80"
              }`}
              onClick={() => focusHotspotById(hotspot.id)}
            >
              {hotspot.name}
            </button>
          ))}
        </div>

        <footer className="mt-2 space-y-1 text-[11px] text-ink/70">
          <p>
            Model:{" "}
            {selectedBuilding?.modelSourceUrl ? (
              <a
                className="underline"
                href={selectedBuilding.modelSourceUrl}
                rel="noreferrer"
                target="_blank"
                onClick={() => track("model_source_click", { building_id: selectedBuildingId })}
              >
                {selectedBuilding.modelAttribution || "Sketchfab source"}
              </a>
            ) : (
              selectedBuilding?.modelAttribution || "Unspecified source"
            )}{" "}
            {selectedBuilding?.modelLicense ? `(${selectedBuilding.modelLicense})` : ""}
          </p>
          <p>Text sources include Wikipedia, NPS, Library of Congress, SF Public Works, and SF Rec & Park.</p>
        </footer>
      </section>

      <section className="flex min-h-[44vh] flex-col rounded-3xl border border-black/10 bg-white/70 p-4 shadow-panel md:min-h-[60vh]">
        <div className="mb-3">
          <h2 className="font-[var(--font-display)] text-lg text-ink">Chat</h2>
          <p className="font-[var(--font-body)] text-sm text-ink/75">
            Answers are grounded to retrieved sources; camera motion is only triggered at high location confidence.
          </p>
        </div>

        <div className="mb-3 rounded-xl border border-black/10 bg-white/60 p-3">
          <div className="mb-2 text-xs font-semibold text-ink/80">Questions to try</div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {promptsToShow.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => {
                  track("try_prompt_click", { prompt });
                  submitMessage(prompt);
                }}
                className="rounded-lg border border-black/10 bg-white px-3 py-2 text-left text-xs hover:bg-[#f3e4d0]"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>

        {activePrimer && (
          <div className="mb-3 rounded-xl border border-[#9a3f22]/25 bg-[#f6eadb] p-3 text-sm">
            <div className="mb-1 flex items-center justify-between">
              <h3 className="font-[var(--font-display)] text-sm text-ink">Focus: {activePrimer.name}</h3>
              <button type="button" className="text-xs text-ink/65 underline" onClick={() => setActivePrimer(null)}>
                Clear
              </button>
            </div>
            <p className="mb-2 text-xs text-ink/85">{activePrimer.overview}</p>
            <div className="mb-1 text-[11px] font-medium text-ink/70">Follow-up ideas</div>
            <div className="flex flex-wrap gap-2">
              {activePrimer.followUps.map((question) => (
                <button
                  key={question}
                  type="button"
                  onClick={() => submitMessage(question)}
                  className="rounded-full border border-black/10 bg-white px-2 py-1 text-[11px] hover:bg-[#efd8bd]"
                >
                  {question}
                </button>
              ))}
            </div>
            <p className="mt-2 text-[10px] text-ink/60">This focus context is included in your next questions.</p>
          </div>
        )}

        <div className="scrollbar-thin mb-3 flex-1 space-y-3 overflow-y-auto rounded-xl border border-black/10 bg-white/55 p-3">
          {messages.map((msg, idx) => (
            <article
              key={`${idx}-${msg.role}`}
              className={`rounded-xl px-3 py-2 text-sm ${msg.role === "user" ? "ml-6 bg-[#f4dfc8]" : "mr-6 bg-[#d9e8e3]"}`}
            >
              <div className="mb-1 text-[10px] uppercase tracking-wide text-black/55">{msg.role}</div>
              <div className="whitespace-pre-wrap">{msg.text}</div>
              {msg.latencyMs ? <div className="mt-1 text-[10px] text-black/55">Latency: {msg.latencyMs}ms</div> : null}
              {msg.citations && msg.citations.length > 0 && (
                <details className="mt-2 rounded-md bg-white/70 p-2">
                  <summary className="cursor-pointer text-xs font-medium">Citations ({msg.citations.length})</summary>
                  <ul className="mt-2 space-y-2 text-xs">
                    {msg.citations.map((c, citationIdx) => (
                      <li key={`${citationIdx}-${c.url}`}>
                        <a
                          className="text-[#9a3f22] underline"
                          href={c.url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={() =>
                            track("citation_click", {
                              building_id: selectedBuildingId,
                              citation_title: c.title,
                            })
                          }
                        >
                          {c.title}
                        </a>
                        <p className="text-black/80">{c.snippet}</p>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </article>
          ))}
          {busy && <p className="text-xs text-ink/70">Thinking... This can take a few seconds on hosted backends.</p>}
        </div>

        <form
          className="flex flex-col gap-2 sm:flex-row"
          onSubmit={(event) => {
            event.preventDefault();
            submitMessage(input);
          }}
        >
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            className="flex-1 rounded-xl border border-black/20 bg-white px-3 py-2 text-sm outline-none focus:border-[#9a3f22]"
            placeholder="Ask about architecture, history, restoration, or details..."
          />
          <button
            disabled={busy || !input.trim()}
            className="rounded-xl bg-[#9a3f22] px-4 py-2 text-sm text-white disabled:opacity-45 sm:min-w-[88px]"
            type="submit"
          >
            Send
          </button>
        </form>

        {notice && <p className="mt-2 text-xs text-[#7a4f1b]">{notice}</p>}
        {error && (
          <div className="mt-2 rounded-lg border border-[#a92222]/25 bg-[#fdeeee] p-2 text-xs text-[#a92222]">
            <p>{error}</p>
            {lastQuestion && (
              <button
                type="button"
                className="mt-1 underline"
                onClick={() => {
                  track("chat_retry_click", { building_id: selectedBuildingId });
                  submitMessage(lastQuestion);
                }}
              >
                Retry last question
              </button>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
