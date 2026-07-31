---
name: messages
description: Read and send iMessages/SMS via the macOS Messages tool. Use when the user asks about their texts, wants to check messages, search conversations, or send a text.
---

# Messages (iMessage / SMS)

Use the `messages` tool directly. All results are JSON.

## Tool Usage

```
messages { action: "recent", limit: 30 }
messages { action: "list", limit: 20 }
messages { action: "conversation", contact: "Contact Name", limit: 30 }
messages { action: "search", query: "search text", limit: 20 }
messages { action: "send", contact: "Contact Name", text: "message text" }
```

## Group Chats

`send` supports group chats. The `contact` field accepts:
- A contact name / phone / email → 1:1 iMessage
- A `chat_identifier` like `chat758926295475402717` or a 32-hex GUID → group chat
- A group chat display name (exact or substring) like `"3031 Lyfe"` → group chat

Resolution order: chat_identifier prefix is matched first; otherwise individual contact is tried, then group display name as fallback.

Get group `chat_identifier`s with `action: "list"`.

## Actions

- **recent** — Get recent messages across all conversations
- **list** — List conversations with last message preview
- **conversation** — Get messages with a specific contact (by name, phone, or email)
- **search** — Search message text
- **send** — Send an iMessage (resolves contact names to phone numbers)

## Summarizing Messages

When asked to check or summarize messages:
1. Use `recent` to get latest messages
2. Group by conversation/contact
3. For each conversation with new activity:
   - Summarize what was discussed
   - Note if a reply seems expected
   - Flag anything time-sensitive (plans, meetups, questions)
4. Don't include full raw message text — summarize instead

## Privacy

- Never include full message bodies in output sent externally (e.g., Telegram)
- Summarize content, don't reproduce it verbatim
- Use contact names as headings, not message content
