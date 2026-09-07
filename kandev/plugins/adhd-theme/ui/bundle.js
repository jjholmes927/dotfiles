const RULES = [
  ["adhd-bad", /^(?:→\s*)?(?:❌|🔴|p0\b|block(?:ed|er)?\b|fail(?:ed|ure)?\b|error\b|broken\b|refuted\b|not verified\b|red\b)/i],
  ["adhd-warn", /^(?:→\s*)?(?:⚠️?|🟡|p1\b|warn(?:ing)?\b|risk\b|caveat\b|gotcha\b|uncertain\b|partial\b|stale\b|pending\b|worth noting\b|watch out\b|unverified\b)/i],
  ["adhd-ok", /^(?:→\s*)?(?:✅|🟢|ok\b|done\b|shipped\b|verified\b|pass(?:ed)?\b|merged\b|confirmed\b|fixed\b|all implemented\b|green\b|resolved\b|complete[d]?\b|works\b)/i],
  ["adhd-ask", /^(?:→\s*)?(?:decision needed|decision\b|question\b|approve\b|gate\b|needs you\b|your call\b|choose\b|pick\b|tl;dr)/i],
  ["adhd-info", /^(?:→\s*)?(?:p[23]\b|also found\b|note\b|fyi\b|context\b|background\b|measured\b|evidence\b|next\b|follow-?ups?\b)/i],
];
const CLASSES = RULES.map((r) => r[0]);

function classify(text) {
  const t = text.replace(/^[\s*_`"'([]+/, "").trim();
  for (const [cls, re] of RULES) if (re.test(t)) return cls;
  return null;
}

function paint(root) {
  const scope = root.querySelectorAll ? root : document;
  scope.querySelectorAll(".markdown-body strong:not([data-adhd]), .markdown-body td:not([data-adhd])").forEach((el) => {
    el.dataset.adhd = "1";
    const cls = classify(el.textContent || "");
    if (!cls) return;
    el.classList.add(cls);
    if (el.tagName === "TD" && el.parentElement && el.cellIndex <= 1 && cls !== "adhd-info" && cls !== "adhd-ask") {
      el.parentElement.classList.add(cls.replace("adhd-", "adhd-row-"));
    }
  });
  scope.querySelectorAll(".markdown-body blockquote:not([data-adhd])").forEach((bq) => {
    bq.dataset.adhd = "1";
    const first = bq.querySelector("p > strong:first-child, p > em:first-child");
    const cls = first ? classify(first.textContent || "") : null;
    if (cls === "adhd-ask") bq.classList.add("adhd-ask");
  });
}

let scheduled = false;
function schedule() {
  if (scheduled) return;
  scheduled = true;
  requestAnimationFrame(() => {
    scheduled = false;
    paint(document);
  });
}

let observer = null;
window.registerKandevPlugin("jjholmes927-adhd-theme", {
  initialize() {
    paint(document);
    observer = new MutationObserver(schedule);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  },
  destroy() {
    if (observer) observer.disconnect();
    observer = null;
    document.querySelectorAll("[data-adhd]").forEach((el) => {
      delete el.dataset.adhd;
      el.classList.remove(...CLASSES, "adhd-row-bad", "adhd-row-warn", "adhd-row-ok");
    });
  },
});
