# Firewall → App back end: what the gateway sends to `/raise`

From A (firewall), for C. Tested against `backend/app.py` as of the `firewall` branch (Nov 15), with no changes to the back end: `tests/seams/test_gateway_core.py` runs your Flask app in a thread.

## Every question

`POST /raise` with JSON. `container_id` is the agent's name (`openclaw` or `hermes`), not a Docker id. `kind` says which pop-up to show. The gateway waits up to 125 s; anything other than `{"decision": "approve"}` counts as a deny.

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

Everything else the gateway decides goes to its stdout as JSON lines (`docker compose logs gateway`), with a `kind` field: `tool_call`, `tool_denied`, `hidden_instruction`, `injection_check`, `model_call`, `model_forwarded`, `model_blocked`, `model_withheld`, `consent`. They hold counts, rule ids, file paths, URLs and masked previews, never the real values behind placeholders or keys. The one exception is `hidden_instruction`, which shows the hidden text found in an email or page (up to 500 characters) as evidence. When you have an endpoint for plain events, `core/firewall/core_client.py` `emit()` is the one place to change.

## Found while testing (please look)

1. **A question is lost when the dashboard reconnects to `/events`.** Each `/events` connection runs a thread that takes the next question off one shared queue. After a page reload, the old connection's thread is still waiting, takes the next question, and fails to send it, so the pop-up never shows and the agent gets a deny after 120 s. A fix: keep unanswered questions (with their details) in `_waiting`, and send all of them to each new `/events` connection.
2. **`/response` accepts an answer from anything on the machine.** It should check a token that only the dashboard has.
