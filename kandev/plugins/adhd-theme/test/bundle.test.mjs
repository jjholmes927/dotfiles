import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../ui/bundle.js", import.meta.url), "utf8");
const context = {
  window: { registerKandevPlugin() {} },
  document: { querySelectorAll: () => [], documentElement: { style: { setProperty() {}, removeProperty() {} } } },
  MutationObserver: class { observe() {} disconnect() {} },
  requestAnimationFrame: () => 0,
  localStorage: { getItem: () => null, setItem() {} },
  location: { href: "http://kandev.test/" },
  URL,
};
vm.createContext(context);
vm.runInContext(source, context);
const { repliesSinceLastAnswer, toPlainText } = context;

const question = (status = "pending") => ({ author_type: "agent", type: "clarification_request", metadata: { status }, content: "q" });
const reply = (content) => ({ author_type: "agent", type: "message", content });
const tool = { author_type: "agent", type: "tool_call", content: "" };
const user = (content) => ({ author_type: "user", type: "message", content });

test("replies between the last answer and the question, oldest first", () => {
  assert.deepEqual([...repliesSinceLastAnswer([question(), reply("b"), tool, reply("a"), question("answered")])], ["a", "b"]);
});

test("a user message also ends the window", () => {
  assert.deepEqual([...repliesSinceLastAnswer([question(), reply("b"), user("go"), reply("a")])], ["b"]);
});

test("the task's own starting prompt is not an answer", () => {
  const start = { author_type: "user", type: "message", content: "/e2e NEV-268", metadata: { auto_start: true } };
  assert.deepEqual([...repliesSinceLastAnswer([question(), reply("progress"), start])], []);
});

test("no earlier answer in view means no pin", () => {
  assert.deepEqual([...repliesSinceLastAnswer([question(), reply("a"), reply("b")])], []);
});

test("no question or no messages means no pin", () => {
  assert.deepEqual([...repliesSinceLastAnswer([reply("a"), user("hi")])], []);
  assert.deepEqual([...repliesSinceLastAnswer([])], []);
});

test("a newest question that is already answered means no pin", () => {
  assert.deepEqual([...repliesSinceLastAnswer([question("answered"), reply("a"), question("answered")])], []);
});

test("blank replies are skipped", () => {
  assert.deepEqual([...repliesSinceLastAnswer([question(), reply("  "), reply("a"), question("answered")])], ["a"]);
});

test("markdown becomes plain text", () => {
  assert.equal(toPlainText("**Done:** see [plan](http://x) `a`"), "Done: see plan a");
  assert.equal(toPlainText("## Heading\n> quoted __bold__"), "Heading\nquoted bold");
});
