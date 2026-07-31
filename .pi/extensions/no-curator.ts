import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

// Force web_search workflow to "none" — skip the curator/approval browser
export default function (pi: ExtensionAPI) {
  pi.on("tool_call", async (event) => {
    if (event.toolName === "web_search") {
      event.input.workflow = "none";
    }
  });
}
