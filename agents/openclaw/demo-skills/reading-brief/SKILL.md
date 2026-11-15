---
name: reading-brief
description: Summarize readings, cross-reference notes or web pages, and draft an email brief.
---

# Reading brief

When the user asks for a reading brief or study summary:

1. Call `heimdall__files_list` to find the available folders and files.
2. Call `heimdall__files_read` on the relevant files. Keep any `{{PLACEHOLDER}}` tokens and `<<confidential:...>>` markers intact.
3. Write a concise summary with:
   - Main claim in one sentence
   - Key evidence or quotes from the text
   - Open questions for discussion
4. If the user asks to share or save the brief, use `heimdall__gmail_draft` or `heimdall__files_write` if those tools are in your tool list.
