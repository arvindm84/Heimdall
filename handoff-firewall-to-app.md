# Firewall → App back end: what the gateway sends to `/api/raise`

From A (firewall), for C. Tested against `backend/app.py` from main (Nov 15, port 8765, routes under `/api`), with no changes to the back end: `tests/seams/test_gateway_core.py` runs your Flask app in a thread.

## Every question

`POST /api/raise` with JSON (the gateway calls `http://host.docker.internal:8765`; `CORE_URL` changes it). `container_id` is the agent's name (`openclaw` or `hermes`), not a Docker id. `kind` says which pop-up to show. The gateway waits up to 125 s; anything other than `{"decision": "approve"}` counts as a deny.

| Field | Always | Meaning |
|---|---|---|
| `kind` | yes | `approval` (an action) or `consent` (Confidential data may leave the machine) |
| `container_id` | yes | the agent's name |
| `question` | yes | one plain sentence for the pop-up, plus details on following lines |
| `tool` | for tool calls | the tool being asked about |

## The questions, by case

| Case | kind | Extra fields |
|---|---|---|
| Write or fetch after reading email or a web page | `approval` | `tool`, `path` (file path or URL) |
| `gmail_send` | `approval` | `tool`, `to`, `subject`, `body`: the final email with real values filled in. Show them: the user approves exactly this |
| `gmail_send` or `web_fetch` after reading a Confidential file | `consent` | as above |
| A model call holding a Confidential file's text | `consent` | `file` (`taxes/return.txt`), `folder` (`taxes`), `provider` (`Gemini`, `Anthropic`). No `tool` |

A consent answer on a model call holds for that file for the rest of the agent's run; a deny is remembered too, so the user isn't asked again on every model call. Until you support `allow_once / always_folder / deny`, `approve` means "allow for this run".

## Events

Everything else the gateway decides goes to its stdout as JSON lines (`docker compose logs gateway`), with a `kind` field: `tool_call`, `tool_denied`, `hidden_instruction`, `injection_check`, `model_call`, `model_forwarded`, `model_blocked`, `model_withheld`, `consent`. They hold counts, rule ids, file paths, URLs and masked previews, never the real values behind placeholders or keys. The one exception is `hidden_instruction`, which shows the hidden text found in an email or page (up to 500 characters) as evidence. The dashboard needs these for the activity feed, the flow map and scene 3's red flag. The gateway is ready: with `HEIMDALL_EVENTS_URL` set it posts each event as one JSON object (the line above) to that URL, in order, without waiting on the answer. Proposed: `POST /api/event` on your back end, which puts the event on the `/events` stream with a field telling the dashboard it is an event, not a question.

## Found while testing (please look)

1. ~~A question is lost when the dashboard reconnects.~~ Fixed on main; the seam test `test_a_reconnected_dashboard_still_gets_the_question` checks it.
2. **`/api/response` accepts an answer from anything on the machine.** It should check a token that only the dashboard has.
