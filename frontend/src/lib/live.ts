// The one live connection to the back end: GET /api/events (Server-Sent Events).
// It carries three kinds of message (see backend/app.py, events()):
//   plain message       a question from the firewall that needs the user's answer -> a pop-up
//   event: resolved     a question was answered or timed out -> close its pop-up
//   event: firewall     a decision the firewall made -> the activity feed and flow map

import { useEffect, useState } from "react";
import { fromGateway, type FirewallEvent } from "../data/events";

// A question from the firewall. `kind`, `container_id` and `question` are always there;
// the rest depends on the case (firewall-integration.md, "POST /api/raise").
export type Question = {
  request_id: string;
  kind: "approval" | "consent";
  container_id: string; // the agent's name
  question: string;
  tool?: string;
  path?: string; // file path or URL
  to?: string; // gmail_send: the real recipient, subject and body. Show, never store or log
  subject?: string;
  body?: string;
  file?: string; // consent on a model call
  folder?: string;
  provider?: string;
};

// The back end keeps at most this many events; keep the same here.
const MAX_EVENTS = 500;

export function useLive() {
  const [questions, setQuestions] = useState<Question[]>([]); // oldest first
  const [events, setEvents] = useState<FirewallEvent[]>([]); // oldest first
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const source = new EventSource("/api/events");

    // On every (re)connect the back end sends everything again: pending questions and
    // recent events. Start from empty so nothing shows twice. This also covers a back-end
    // restart, where event ids start again at 1.
    source.onopen = () => {
      setConnected(true);
      setQuestions([]);
      setEvents([]);
    };
    // The browser reconnects by itself after an error.
    source.onerror = () => setConnected(false);

    source.onmessage = (m) => {
      const q = JSON.parse(m.data) as Question;
      setQuestions((all) => (all.some((x) => x.request_id === q.request_id) ? all : [...all, q]));
    };
    source.addEventListener("resolved", (m) => {
      const { request_id } = JSON.parse((m as MessageEvent).data);
      setQuestions((all) => all.filter((q) => q.request_id !== request_id));
    });
    source.addEventListener("firewall", (m) => {
      const event = fromGateway(JSON.parse((m as MessageEvent).data));
      if (event) setEvents((all) => [...all, event].slice(-MAX_EVENTS));
    });

    return () => source.close();
  }, []);

  return { questions, events, connected };
}
