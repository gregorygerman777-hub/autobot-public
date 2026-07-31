import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

export default function (pi: ExtensionAPI) {
  pi.on("before_agent_start", async (event, ctx) => {
    const memoryDir = join(ctx.cwd, "data", "memory");
    if (!existsSync(memoryDir)) return;

    const parts: string[] = [];

    const profilePath = join(memoryDir, "profile.md");
    if (existsSync(profilePath)) {
      parts.push(readFileSync(profilePath, "utf-8"));
    }

    const prefsPath = join(memoryDir, "preferences.md");
    if (existsSync(prefsPath)) {
      parts.push(readFileSync(prefsPath, "utf-8"));
    }

    // Load yesterday's journal if it exists
    const yesterday = new Date(Date.now() - 86400000);
    const yStr = yesterday.toISOString().slice(0, 10);
    const journalPath = join(memoryDir, "journal", `${yStr}.md`);
    if (existsSync(journalPath)) {
      parts.push(`# Yesterday's Journal (${yStr})\n${readFileSync(journalPath, "utf-8")}`);
    }

    if (parts.length > 0) {
      const context = parts.join("\n\n");
      return {
        systemPrompt: event.systemPrompt + "\n\n<memory>\n" + context + "\n</memory>",
      };
    }
  });
}
