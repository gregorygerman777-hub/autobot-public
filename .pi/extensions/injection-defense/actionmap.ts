/**
 * Maps concrete tool calls onto registered action names.
 *
 * The registry in `autobot_core/actions.py` names capabilities; this file
 * recognizes them in the wild. Anything not matched here is treated as a read
 * and passes through -- the action guard is not a general sandbox, it is a
 * gate on the specific side effects the 12 skills document.
 */

export interface MappedAction {
  action: string;
  target: string;
}

const OSASCRIPT_APP = /tell\s+application\s+"(Contacts|Calendar|Reminders)"/i;

/** Recognize a side-effecting action in a bash command string. */
function mapBash(command: string): MappedAction | null {
  // --- Gmail egress ----------------------------------------------------
  if (/\bgws\s+gmail\b/i.test(command) && /\bmessages\s+send\b|\+send\b/i.test(command)) {
    return { action: "gmail.send", target: "gmail" };
  }
  // The skill documents a raw-API path that bypasses the gws CLI entirely.
  if (/googleapiclient|gmail['"]?,\s*['"]v1['"]/i.test(command) && /\.send\(/i.test(command)) {
    return { action: "gmail.send", target: "gmail-api" };
  }
  if (/credentials\.enc|\.encryption_key/i.test(command)) {
    return { action: "gmail.send", target: "gmail-credentials" };
  }

  // --- macOS app mutation via AppleScript ------------------------------
  const app = command.match(OSASCRIPT_APP)?.[1]?.toLowerCase();
  if (app) {
    const deletes = /\bdelete\b/i.test(command);
    const makes = /\bmake\s+new\b/i.test(command);
    const sets = /\bset\s+(value|name|due date|summary)\b/i.test(command);

    if (app === "contacts") {
      if (deletes) return { action: "contacts.delete", target: "contacts" };
      if (makes && /make new (phone|email)/i.test(command) && !/make new person/i.test(command)) {
        return { action: "contacts.update", target: "contacts" };
      }
      if (makes) return { action: "contacts.create", target: "contacts" };
      if (sets) return { action: "contacts.update", target: "contacts" };
    }
    if (app === "calendar") {
      if (deletes) return { action: "calendar.delete", target: "calendar" };
      if (makes) return { action: "calendar.create", target: "calendar" };
    }
    if (app === "reminders") {
      if (deletes) return { action: "reminders.delete", target: "reminders" };
      if (makes) return { action: "reminders.create", target: "reminders" };
    }
  }

  // --- Browser automation ----------------------------------------------
  if (/browser-eval\.js/i.test(command)) return { action: "browser.eval", target: "browser" };
  if (/school-submit\.js|browser-upload\.js/i.test(command)) {
    return { action: "browser.submit", target: "browser" };
  }

  // --- GPU spend --------------------------------------------------------
  if (/prime_intellect\b/i.test(command)) {
    if (/\bcreate\b/i.test(command)) return { action: "prime.create_pod", target: "prime" };
    if (/\bterminate\b/i.test(command)) return { action: "prime.terminate_pod", target: "prime" };
  }

  return null;
}

/** Recognize memory writes, which are ordinary file writes to a sensitive path. */
function mapMemoryWrite(path: string): MappedAction | null {
  const p = path.replace(/\\/g, "/");
  if (!/data\/memory\//.test(p)) return null;
  if (/data\/memory\/(journal|scratch|sessions)\//.test(p)) {
    return { action: "memory.write_journal", target: p };
  }
  return { action: "memory.write_semantic", target: p };
}

export function mapToolCall(
  toolName: string,
  input: Record<string, unknown>,
): MappedAction | null {
  const action = String(input?.action ?? "").toLowerCase();

  switch (toolName) {
    case "bash":
      return mapBash(String(input?.command ?? ""));

    case "messages":
      if (action === "send") {
        return { action: "messages.send", target: String(input?.contact ?? "") };
      }
      return null;

    case "school":
      if (action === "submit") {
        return { action: "school.submit", target: String(input?.assignmentId ?? "") };
      }
      return null;

    case "notion":
      if (action === "create-page" || action === "update-page") {
        return { action: "notion.write", target: action };
      }
      return null;

    case "telegram":
    case "telebridge": {
      // Sending to the pre-configured owner chat is the pre-approved path;
      // anything that names a different destination is not.
      const chat = String(input?.chatId ?? input?.chat_id ?? "");
      const configured = process.env.TELEGRAM_CHAT_ID ?? "";
      if (!chat || (configured && chat === configured)) {
        return { action: "telegram.send_owner", target: chat || "owner" };
      }
      return { action: "telegram.send_other", target: chat };
    }

    case "write":
    case "edit":
      return mapMemoryWrite(String(input?.path ?? input?.file_path ?? ""));

    default:
      return null;
  }
}
