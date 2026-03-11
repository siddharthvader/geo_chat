"use client";

type EventProps = Record<string, string | number | boolean | null | undefined>;

declare global {
  interface Window {
    dataLayer?: Array<Record<string, unknown>>;
  }
}

export function track(event: string, props: EventProps = {}): void {
  if (typeof window === "undefined") {
    return;
  }

  const payload: Record<string, unknown> = {
    event,
    ts: Date.now(),
    ...props,
  };

  window.dispatchEvent(new CustomEvent("buildingtalk:analytics", { detail: payload }));

  if (Array.isArray(window.dataLayer)) {
    window.dataLayer.push(payload);
  }

  if (process.env.NEXT_PUBLIC_ANALYTICS_DEBUG === "true") {
    // eslint-disable-next-line no-console
    console.info("[analytics]", payload);
  }
}
