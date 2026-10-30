"use client";
import Script from "next/script";
import { useEffect, useRef, useState } from "react";

type Api = { render(element: HTMLElement, options: Record<string, unknown>): string; remove(id: string): void };
declare global { interface Window { turnstile?: Api } }
/** Only the public site key reaches the browser. Supabase verifies each token. */
export function Turnstile({onToken, attempt}: {onToken: (token: string) => void; attempt: number}) {
  const element = useRef<HTMLDivElement>(null);
  const callback = useRef(onToken);
  useEffect(() => { callback.current = onToken; }, [onToken]);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const sitekey = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY;
  useEffect(() => {
    if (!ready || !sitekey || !element.current || !window.turnstile) return;
    const api = window.turnstile;
    let active = true;
    callback.current("");
    let id: string | undefined;
    try {
      id = api.render(element.current, {
        sitekey, theme: "auto", "response-field": false,
        callback: (token: string) => { if (active) { setError(""); callback.current(token); } },
        "expired-callback": () => { if (active) { callback.current(""); setError("Verification expired. Please complete the new challenge."); } },
        "timeout-callback": () => { if (active) { callback.current(""); setError("Verification timed out. Please try again."); } },
        "error-callback": () => { if (active) { callback.current(""); setError("Verification unavailable. Check your connection and try again."); } },
      });
    } catch { callback.current(""); }
    return () => { active = false; callback.current(""); if (id !== undefined) api.remove(id); };
  }, [ready, sitekey, attempt]);
  return <div aria-label="Bot protection">
    {sitekey ? <Script id="mesh-turnstile" src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit" strategy="afterInteractive" onReady={() => setReady(true)} onError={() => { callback.current(""); setError("Verification could not load. Check your connection and reload."); }} /> : <p role="alert">Bot protection is not configured. Sign-in is unavailable.</p>}
    <div ref={element} />
    {error && <p role="alert" className="text-sm text-ink-2">{error}</p>}
  </div>;
}
