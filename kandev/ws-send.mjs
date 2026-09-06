const [taskId, sessionId, ...rest] = process.argv.slice(2);
const content = rest.join(" ");
const base = process.env.KANDEV_BASE || "http://127.0.0.1:38429";
if (!taskId || !sessionId || !content) {
  console.error("usage: ws-send.mjs <task_id> <session_id> <content...>");
  process.exit(2);
}
const ws = new WebSocket(base.replace(/^http/, "ws") + "/ws");
const send = (id, action, payload) => ws.send(JSON.stringify({ id, type: "request", action, payload }));
const fail = (why) => { console.error(why); process.exit(1); };
setTimeout(() => fail("timeout waiting for kandev websocket"), 15000);
ws.onerror = (e) => fail(`websocket error: ${e.message || e.type}`);
ws.onopen = () => send("q1", "message.queue.add", { task_id: taskId, session_id: sessionId, content });
ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.id === "q1") {
    if (m.type === "error") fail(`queue.add failed: ${JSON.stringify(m.payload).slice(0, 300)}`);
    const entry = m.payload?.entry?.id || m.payload?.entry_id || m.payload?.id;
    send("q2", "message.queue.send_now", { session_id: sessionId, scope: "entry", entry_id: entry });
  }
  if (m.id === "q2") {
    if (m.type === "error") fail(`send_now failed: ${JSON.stringify(m.payload).slice(0, 300)}`);
    console.log("sent");
    ws.close();
    process.exit(0);
  }
};
