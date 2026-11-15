// Plain-language names for firewall tools, so the UI never shows raw ids like "files_read".

// As a capability: "Can: Read files, Draft email"
export const TOOL_NAME: Record<string, string> = {
  files_read: "Read files",
  files_list: "List files",
  files_write: "Write files",
  gmail_read: "Read email",
  gmail_draft: "Draft email",
  gmail_send: "Send email",
  web_fetch: "Open web pages",
  memory_read: "Read notes",
  memory_write: "Save notes",
  messages: "Talk to the AI model",
};

// As an attempted action, followed by the target: "OpenClaw wanted to read ~/.env"
export const TOOL_VERB: Record<string, string> = {
  files_read: "read",
  files_list: "list the files in",
  files_write: "write",
  gmail_read: "read the email",
  gmail_draft: "draft an email to",
  gmail_send: "send an email to",
  web_fetch: "open",
  memory_read: "read its notes",
  memory_write: "save a note",
  messages: "send a message to",
};
