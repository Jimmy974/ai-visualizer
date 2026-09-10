#!/usr/bin/env python3
# Tests for board card display: cards.js view/poller logic and HTML seams.
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BOARD = REPO / "faces" / "board"
CARDS_JS = BOARD / "cards.js"
CARDS_CSS = BOARD / "cards.css"
INDEX = BOARD / "index.html"
NODE = shutil.which("node")

JS_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const path = process.argv[1];
const code = fs.readFileSync(path, "utf8");
const document = {
  visibilityState: "visible",
  readyState: "complete",
  body: { classList: { contains: () => false } },
  getElementById: () => null,
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener: () => {},
};
const window = { document };
const ctx = {
  window, document, console, setTimeout, clearTimeout,
  Date, Intl, JSON, Math, Number, String, Array, Promise, Object,
};
vm.runInNewContext(code, ctx);
const BC = ctx.window.BoardCards || ctx.BoardCards;
if (!BC) { console.error("BoardCards missing"); process.exit(2); }

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const results = [];
function test(name, fn) {
  return Promise.resolve()
    .then(fn)
    .then(() => results.push({name, ok: true}))
    .catch((err) => results.push({name, ok: false, error: String(err && err.stack || err)}));
}

const sevenTasks = [];
for (let i = 1; i <= 7; i++) sevenTasks.push({id: "t"+i, title: "Task "+i, dueDate: "2026-03-29"});
sevenTasks[0].title = "<b>html</b>";
sevenTasks[1].title = "X".repeat(500);

const fiveEvents = [
  {id:"e1", title:"All day off", allDay:true, startDate:"2026-03-29", endDate:"2026-03-30"},
  {id:"e2", title:"Call", allDay:false, start:"2026-03-29T00:30:00Z", end:"2026-03-29T02:30:00Z"},
  {id:"e3", title:"Later", allDay:false, start:"2026-03-29T12:00:00Z", end:"2026-03-29T13:00:00Z"},
  {id:"e4", title:"Next", allDay:false, start:"2026-03-30T09:00:00Z", end:"2026-03-30T10:00:00Z"},
  {id:"e5", title:"Last", allDay:false, start:"2026-03-30T11:00:00Z", end:"2026-03-30T12:00:00Z"},
];

Promise.resolve()
.then(() => test("dst london times", () => {
  assert(BC.formatHM("2026-03-29T00:30:00Z", "Europe/London") === "00:30", "start");
  assert(BC.formatHM("2026-03-29T02:30:00Z", "Europe/London") === "03:30", "end");
}))
.then(() => test("all-day label and date-only", () => {
  const cal = {
    id:"calendar", status:"ready", attemptedAt:"2026-03-29T12:00:00Z",
    updatedAt:"2026-03-29T12:00:00Z", totalCount:1,
    timezone:"Europe/London", range:{start:"2026-03-29", end:"2026-03-30"},
    items:[{id:"e1", title:"All day off", allDay:true, startDate:"2026-03-29", endDate:"2026-03-30"}],
  };
  const view = BC.panelView(cal, {timeZone:"Europe/London"});
  assert(view.items[0].meta.indexOf("All day") !== -1, "All day");
  assert(view.items[0].meta.indexOf("2026-03-29") !== -1, "date stays");
  assert(view.rangeLabel.indexOf("2026-03-29") !== -1, "range start");
  assert(view.rangeLabel.indexOf("2026-03-30") !== -1, "range exclusive end");
  assert(view.timezone === "Europe/London", "tz");
}))
.then(() => test("overflow 5 tasks and 3 events", () => {
  const todo = BC.panelView({
    id:"todo", status:"ready", attemptedAt:"2026-03-29T12:00:00Z",
    updatedAt:"2026-03-29T12:00:00Z", totalCount:7, items:sevenTasks,
  }, {});
  assert(todo.items.length === 5, "five tasks");
  assert(todo.overflow === 2, "task overflow");
  assert(todo.items[0].title === "<b>html</b>", "literal title");
  assert(todo.items[1].title.length === 500, "long title");
  const cal = BC.panelView({
    id:"calendar", status:"ready", attemptedAt:"2026-03-29T12:00:00Z",
    updatedAt:"2026-03-29T12:00:00Z", totalCount:5,
    timezone:"Europe/London", range:{start:"2026-03-29", end:"2026-03-31"},
    items:fiveEvents,
  }, {timeZone:"Europe/London"});
  assert(cal.items.length === 3, "three events");
  assert(cal.overflow === 2, "event overflow");
}))
.then(() => test("calendar sort all-day first within day", () => {
  const items = [
    {id:"t", title:"Timed first", allDay:false, start:"2026-03-29T08:00:00Z", end:"2026-03-29T09:00:00Z"},
    {id:"a", title:"All day", allDay:true, startDate:"2026-03-29", endDate:"2026-03-30"},
  ];
  const sorted = BC.sortCalendarItems(items);
  assert(sorted[0].id === "a", "all-day first");
}))
.then(() => test("invitation empty snapshot", () => {
  const snap = BC.snapshotView({version:1, cards:[]}, {});
  assert(snap.todo.mode === "invitation", "todo invite");
  assert(snap.calendar.mode === "invitation", "cal invite");
  assert(snap.todo.statusText.indexOf("JARVIS") !== -1, "default name");
  assert(snap.todo.statusText.indexOf("Sinner") === -1, "no hard-coded Sinner");
  const named = BC.snapshotView({version:1, cards:[]}, {agentName:"Orion"});
  assert(named.todo.statusText.indexOf("Orion") !== -1, "configured name");
  assert(snap.todo.items.length === 0, "no fake todo");
  assert(snap.calendar.items.length === 0, "no fake cal");
  assert(!snap.calendar.rangeLabel, "no invented range");
}))
.then(() => test("loading and error retain success including range", () => {
  const ready = {
    id:"calendar", status:"loading", attemptedAt:"2026-03-29T14:00:00Z",
    updatedAt:"2026-03-29T12:00:00Z", totalCount:1,
    timezone:"Europe/London", range:{start:"2026-03-29", end:"2026-03-30"},
    items:[{id:"e1", title:"Kept", allDay:true, startDate:"2026-03-29", endDate:"2026-03-30"}],
  };
  const loading = BC.panelView(ready, {timeZone:"Europe/London"});
  assert(loading.mode === "loading", "loading mode");
  assert(loading.items.length === 1, "kept items");
  assert(loading.rangeLabel.indexOf("2026-03-29") !== -1, "kept range");
  assert(loading.updatedLabel, "kept updated");
  const errCard = Object.assign({}, ready, {status:"error", message:"<b>boom</b>"});
  const err = BC.panelView(errCard, {timeZone:"Europe/London"});
  assert(err.mode === "error", "error mode");
  assert(err.items[0].title === "Kept", "error keeps items");
  assert(err.message === "<b>boom</b>", "message as text");
  assert(err.rangeLabel.indexOf("2026-03-29") !== -1, "error keeps range");
}))
.then(() => test("first fetch failure invents no scope", () => {
  const view = BC.panelView({
    id:"calendar", status:"error", attemptedAt:"2026-03-29T10:00:00Z",
    message:"provider failed",
  }, {});
  assert(view.mode === "error", "error");
  assert(view.items.length === 0, "no items");
  assert(!view.rangeLabel, "no range");
  assert(!view.timezone, "no tz");
  assert(!view.updatedLabel, "no updated");
}))
.then(() => test("successful empty replaces items", () => {
  const view = BC.panelView({
    id:"todo", status:"ready", attemptedAt:"2026-03-29T15:00:00Z",
    updatedAt:"2026-03-29T15:00:00Z", totalCount:0, items:[],
  }, {});
  assert(view.mode === "empty", "empty");
  assert(view.items.length === 0, "cleared");
}))
.then(() => test("connection error retains last snapshot", () => {
  const last = {version:1, cards:[{
    id:"todo", status:"ready", attemptedAt:"2026-03-29T12:00:00Z",
    updatedAt:"2026-03-29T12:00:00Z", totalCount:1,
    items:[{id:"t1", title:"Buy milk", dueDate:"2026-03-29"}],
  }]};
  const view = BC.snapshotView(last, {connectionError:true});
  assert(view.todo.mode === "unavailable", "unavailable");
  assert(view.todo.items[0].title === "Buy milk", "retained");
  assert(view.todo.updatedLabel, "dated");
  const none = BC.snapshotView({version:1, cards:[]}, {connectionError:true});
  assert(none.todo.items.length === 0, "no fakes");
  assert(none.todo.mode === "unavailable", "unavailable empty");
}))
.then(() => test("key guard panels and future controls", () => {
  const panel = { closest: (sel) => sel.indexOf(".board-card") !== -1 ? {} : null };
  const child = { closest: (sel) => sel.indexOf(".board-card") !== -1 ? {} : null };
  const body = { closest: () => null, tagName: "BODY" };
  const input = { closest: (sel) => sel.indexOf("input") !== -1 ? {} : null, tagName: "INPUT" };
  assert(BC.shouldIgnoreGlobalKeys(panel) === true, "panel");
  assert(BC.shouldIgnoreGlobalKeys(child) === true, "child");
  assert(BC.shouldIgnoreGlobalKeys(body) === false, "body");
  assert(BC.shouldIgnoreGlobalKeys(input) === true, "future input");
  assert(BC.shouldIgnoreGlobalKeys(null) === false, "null");
}))
.then(() => test("poller one in flight hidden pause resume", () => {
  let now = 0;
  let hidden = false;
  const scheduled = [];
  const fetches = [];
  let resolvers = [];
  const fetchFn = () => {
    fetches.push(now);
    return new Promise((resolve) => {
      resolvers.push(() => resolve({status:200, body:{version:1, cards:[]}}));
    });
  };
  const poller = BC.createPoller({
    intervalMs: 2000,
    fetchFn,
    isHidden: () => hidden,
    onPayload: () => {},
    onConnectionError: () => {},
    setTimeoutFn: (fn, ms) => {
      const id = scheduled.length + 1;
      scheduled.push({id, fn, fireAt: now + ms});
      return id;
    },
    clearTimeoutFn: (id) => {
      const i = scheduled.findIndex((s) => s.id === id);
      if (i >= 0) scheduled.splice(i, 1);
    },
  });
  function flush() {
    return Promise.resolve()
      .then(() => Promise.resolve())
      .then(() => Promise.resolve())
      .then(() => Promise.resolve());
  }
  poller.start();
  assert(fetches.length === 1, "immediate fetch");
  poller.onVisibilityChange();
  assert(fetches.length === 1, "one in flight");
  resolvers.shift()();
  return flush().then(() => {
    assert(fetches.length === 2, "queued kick after in-flight");
    resolvers.shift()();
    return flush();
  }).then(() => {
    assert(scheduled.length === 1, "armed");
    assert(scheduled[0].fireAt === now + 2000, "2s interval");
    hidden = true;
    poller.onVisibilityChange();
    now += 2000;
    const t = scheduled.shift();
    if (t) t.fn();
    assert(fetches.length === 2, "no fetch while hidden");
    hidden = false;
    poller.onVisibilityChange();
    assert(fetches.length === 3, "fetch on return");
    resolvers.shift()();
    return flush();
  }).then(() => {
    assert(scheduled.length === 1, "re-armed after return");
  });
}))
.then(() => {
  const failed = results.filter((r) => !r.ok);
  if (failed.length) {
    console.error(JSON.stringify({ok:false, results}, null, 2));
    process.exit(1);
  }
  console.log(JSON.stringify({ok:true, results}));
})
.catch((err) => {
  console.error(err && err.stack || err);
  process.exit(1);
});
"""


class TestBoardMarkup(unittest.TestCase):
    def test_index_wires_isolated_card_files_and_panels(self):
        html = INDEX.read_text()
        self.assertIn('href="cards.css"', html)
        self.assertIn('src="cards.js"', html)
        self.assertNotIn("core.js", (CARDS_JS.read_text() if CARDS_JS.exists() else ""))
        self.assertNotIn("/state", (CARDS_JS.read_text() if CARDS_JS.exists() else ""))
        todo_at = html.find('id="card-todo"')
        cal_at = html.find('id="card-calendar"')
        self.assertGreater(todo_at, 0)
        self.assertGreater(cal_at, todo_at)
        for card_id, heading in (("card-todo", "card-todo-heading"),
                                 ("card-calendar", "card-calendar-heading")):
            chunk = html[html.find('id="%s"' % card_id): html.find('id="%s"' % card_id) + 500]
            self.assertIn('role="region"', chunk)
            self.assertIn('tabindex="0"', chunk)
            self.assertIn('aria-labelledby="%s"' % heading, chunk)
            self.assertIn('id="%s"' % heading, html)
        self.assertIn("shouldIgnoreGlobalKeys", html)
        self.assertIn("BoardCards", html)
        self.assertNotIn("Sinner", html)
        self.assertNotIn("Sinner", CARDS_JS.read_text())

    def test_css_covers_focus_cursor_cine_and_narrow_stack(self):
        css = CARDS_CSS.read_text()
        self.assertIn(":focus", css)
        self.assertIn("cursor", css)
        self.assertIn("cine", css)
        self.assertIn("@media", css)
        self.assertIn("overflow", css)
        media = css.split("@media")[-1]
        self.assertIn("max-width", media)
        self.assertRegex(media, r"top\s*:\s*\d+px")
        self.assertNotIn("inset: 0", media)
        self.assertNotIn("inset:0", media)


@unittest.skipUnless(NODE, "node is required to execute cards.js tests")
class TestCardsJs(unittest.TestCase):
    def test_cards_js_logic(self):
        self.assertTrue(CARDS_JS.is_file(), "cards.js missing")
        proc = subprocess.run(
            [NODE, "-e", JS_HARNESS, str(CARDS_JS)],
            cwd=str(REPO),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"], payload)


if __name__ == "__main__":
    unittest.main()
