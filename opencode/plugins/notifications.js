import { execFile } from "node:child_process";
import { open } from "node:fs/promises";
import { promisify } from "node:util";

const run = promisify(execFile);

export const Notifications = async () => ({
  event: async ({ event }) => {
    if (
      !["session.idle", "permission.asked", "question.asked"].includes(
        event.type,
      )
    ) {
      return;
    }
    if (!process.env.TMUX || !process.env.TMUX_PANE) return;
    try {
      const { stdout } = await run("tmux", [
        "display-message",
        "-p",
        "-t",
        process.env.TMUX_PANE,
        "#{pane_tty}",
      ]);
      const tty = stdout.trim();
      if (!tty.startsWith("/dev/")) return;
      const handle = await open(tty, "w");
      try {
        await handle.write("\u0007");
      } finally {
        await handle.close();
      }
    } catch {
      // A detached or closed tmux pane must not interrupt the agent.
    }
  },
});
