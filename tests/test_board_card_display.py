#!/usr/bin/env python3
# ai-visualizer: give your AI agent a face.
# Copyright (C) 2026 Jared Rhodenizer
#
# SPDX-License-Identifier: AGPL-3.0-or-later
# Tests for board card display: cards.js view/poller logic and HTML seams.
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BOARD = REPO / "faces" / "board"
CARDS_JS = BOARD / "cards.js"
CARDS_CSS = BOARD / "cards.css"
INDEX = BOARD / "index.html"
NODE = shutil.which("node")

JS_PREAMBLE = r"""
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

"""

JS_HARNESS = JS_PREAMBLE + r"""
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
.then(() => test("hud clearance takes lowest visible HUD bottom plus gap", () => {
  assert(typeof BC.hudClearance === "function", "hudClearance exported");
  const brand = {bottom: 80, width: 300, height: 46};
  const status = {bottom: 160.4, width: 200, height: 126};
  assert(BC.hudClearance([brand, status]) === 177, "default 16px gap, ceil");
  assert(BC.hudClearance([brand, status], 0) === 161, "custom gap");
  assert(BC.hudClearance([status, brand], 10) === 171, "order independent");
  assert(BC.hudClearance([{bottom: 500, width: 0, height: 0}, brand], 0) === 80, "hidden ignored");
  assert(BC.hudClearance([], 16) === 0, "nothing measured -> 0 (keep CSS fallback)");
  assert(BC.hudClearance(null) === 0, "null safe");
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
        match = re.search(r"top\s*:\s*(\d+)px", media)
        self.assertIsNotNone(match)
        self.assertGreaterEqual(int(match.group(1)), 200)
        self.assertNotIn("inset: 0", media)
        self.assertNotIn("inset:0", media)


    def test_narrow_layout_keeps_transcript_line_clear_of_cards(self):
        css = CARDS_CSS.read_text()
        media = css.split("@media")[-1]
        # The transcript line is capped, so a fixed offset can clear it.
        echo = re.search(r"#echo\s*\{([^}]*)\}", media)
        self.assertIsNotNone(echo, "narrow layout must bound #echo")
        cap = re.search(r"max-height\s*:\s*(\d+)px", echo.group(1))
        self.assertIsNotNone(cap, "#echo needs a max-height in the narrow layout")
        self.assertRegex(echo.group(1), r"overflow\s*:\s*hidden")
        base = re.search(r"#echo\{[^}]*?bottom\s*:\s*(\d+)px", INDEX.read_text())
        self.assertIsNotNone(base, "index.html #echo bottom offset not found")
        region = re.search(r"#board-cards\s*\{([^}]*)\}", media)
        self.assertIsNotNone(region)
        bottom = re.search(r"bottom\s*:\s*(\d+)px", region.group(1))
        self.assertIsNotNone(bottom)
        # Cards region must end above the top edge of a full-height #echo.
        self.assertGreaterEqual(
            int(bottom.group(1)), int(base.group(1)) + int(cap.group(1)))
        # Cards still get room: stays below the HUD (top >= 200) without inset: 0.
        top = re.search(r"top\s*:\s*(\d+)px", region.group(1))
        self.assertIsNotNone(top)
        self.assertGreaterEqual(int(top.group(1)), 200)


    def test_wide_layout_clears_hud_via_measured_variable(self):
        css = CARDS_CSS.read_text()
        wide = css.split("@media")[0]
        block = wide[wide.find("#board-cards {"):]
        block = block[:block.find("}")]
        # Top offset comes from the measured HUD bottom, never a fixed 108px.
        self.assertIn("--hud-clear:", block)
        self.assertIn("--cards-top: max(108px, var(--hud-clear))", block)
        self.assertRegex(block, r"padding:\s*var\(--cards-top\)")
        self.assertNotIn("padding: 108px", block)
        # Panels shrink with the offset so they stay above the bottom bar.
        self.assertIn("max-height: calc(100vh - var(--cards-top)", wide)
        js = CARDS_JS.read_text()
        self.assertIn('setProperty("--hud-clear"', js)
        self.assertIn("ResizeObserver", js)
        self.assertIn('addEventListener("resize"', js)
        for sel in ("#brand", "#statusblock"):
            self.assertIn('"%s"' % sel, js)


@unittest.skipUnless(NODE, "node is required to execute cards.js tests")
class TestCardsJs(unittest.TestCase):
    def test_all_day_multi_day_shows_start_and_last_day(self):
        script = JS_PREAMBLE + r"""
// One panel per item: the calendar panel shows at most CAL_LIMIT rows.
const meta = (item) => BC.panelView({
  id:"calendar", status:"ready", attemptedAt:"2026-03-29T12:00:00Z",
  updatedAt:"2026-03-29T12:00:00Z", totalCount:1,
  timezone:"Europe/London", range:{start:"2026-03-29", end:"2026-04-02"}, items:[item],
}, {timeZone:"Europe/London"}).items[0].meta;
const day = (id, s, e) => ({id, title:id, allDay:true, startDate:s, endDate:e});
console.log(JSON.stringify({
  multi: meta(day("multi", "2026-03-29", "2026-04-01")),
  single: meta(day("single", "2026-03-29", "2026-03-30")),
  month: meta(day("month", "2026-02-27", "2026-03-02")),
  noend: meta(day("noend", "2026-03-29", undefined)),
  badend: meta(day("badend", "2026-03-29", "soon")),
}));
"""
        proc = subprocess.run(
            [NODE, "-e", script, str(CARDS_JS)],
            cwd=str(REPO), capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        by_title = json.loads(proc.stdout)
        # endDate is exclusive: 04-01 means the event ends on 03-31.
        self.assertIn("All day", by_title["multi"])
        self.assertIn("2026-03-29", by_title["multi"])
        self.assertIn("2026-03-31", by_title["multi"])
        self.assertNotIn("2026-04-01", by_title["multi"])
        # A one-day event (endDate = startDate + 1) still shows exactly one date.
        self.assertIn("All day", by_title["single"])
        self.assertEqual(re.findall(r"\d{4}-\d{2}-\d{2}", by_title["single"]), ["2026-03-29"])
        # Last day crosses a month boundary correctly (02-27 .. 03-02 exclusive).
        self.assertIn("2026-03-01", by_title["month"])
        self.assertNotIn("2026-03-02", by_title["month"])
        # Missing or malformed endDate falls back to the start date alone.
        for key in ("noend", "badend"):
            self.assertIn("All day", by_title[key])
            self.assertEqual(re.findall(r"\d{4}-\d{2}-\d{2}", by_title[key]), ["2026-03-29"])

    def test_transcript_pins_to_newest_text(self):
        script = JS_PREAMBLE + r"""
// Fake #echo: scrollHeight grows as lines are added; pinToEnd must follow it.
const el = {scrollHeight: 42, scrollTop: 0};
let notify = null;
let observed = null;
function FakeObserver(cb) { notify = cb; this.observe = (t, o) => { observed = {t, o}; }; }
BC.watchTranscript(el, FakeObserver);
const out = {};
out.initial = el.scrollTop;
out.observesEcho = observed && observed.t === el;
out.watchesText = !!(observed && observed.o.childList && observed.o.characterData && observed.o.subtree);
el.scrollHeight = 98;          // 7 lines of 14px
notify();
out.afterGrow = el.scrollTop;
el.scrollHeight = 70;          // text shrank to 5 lines
notify();
out.afterShrink = el.scrollTop;
BC.watchTranscript(null, FakeObserver);   // #echo missing: no-op, no throw
BC.pinToEnd(null);
BC.pinToEnd({});
console.log(JSON.stringify(out));
"""
        proc = subprocess.run(
            [NODE, "-e", script, str(CARDS_JS)],
            cwd=str(REPO), capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        out = json.loads(proc.stdout)
        self.assertEqual(out["initial"], 42)
        self.assertTrue(out["observesEcho"])
        self.assertTrue(out["watchesText"])
        self.assertEqual(out["afterGrow"], 98)     # scrolled to the end: newest lines visible
        self.assertEqual(out["afterShrink"], 70)
        # init wires it to the real #echo.
        self.assertIn('watchTranscript(document.getElementById("echo"))', CARDS_JS.read_text())

    # ── calendar order: card.timezone, never the browser's zone ──────────
    BROWSER_ZONES = ("Asia/Tokyo", "Europe/London", "America/Los_Angeles")

    # Fixtures: (card timezone, items in input order). Ids name the expected slot.
    SORT_FIXTURES = {
        # checks/pilot3.mjs section D: 23:30Z on the 28th is still the 28th in London.
        "check_d": ("Europe/London", [
            {"id": "allday", "title": "All day on the 29th", "allDay": True,
             "startDate": "2026-03-29", "endDate": "2026-03-30"},
            {"id": "late", "title": "Late on the 28th", "allDay": False,
             "start": "2026-03-28T23:30:00Z", "end": "2026-03-28T23:50:00Z"},
        ]),
        # London clocks go forward at 01:00Z on 2026-03-29 (GMT -> BST).
        "london_dst": ("Europe/London", [
            {"id": "a30", "title": "a30", "allDay": True, "startDate": "2026-03-30", "endDate": "2026-03-31"},
            {"id": "t30_0030bst", "title": "t", "allDay": False,
             "start": "2026-03-29T23:30:00Z", "end": "2026-03-29T23:45:00Z"},
            {"id": "t29_0230bst", "title": "t", "allDay": False,
             "start": "2026-03-29T01:30:00Z", "end": "2026-03-29T02:00:00Z"},
            {"id": "a29", "title": "a29", "allDay": True, "startDate": "2026-03-29", "endDate": "2026-03-30"},
            {"id": "t29_0030gmt", "title": "t", "allDay": False,
             "start": "2026-03-29T00:30:00Z", "end": "2026-03-29T00:45:00Z"},
            {"id": "t28_2359", "title": "t", "allDay": False,
             "start": "2026-03-28T23:59:00Z", "end": "2026-03-29T00:10:00Z"},
        ]),
        # Auckland is UTC+13 here: 12:30Z on the 28th is 01:30 on the 29th.
        "auckland": ("Pacific/Auckland", [
            {"id": "t29_0130", "title": "t", "allDay": False,
             "start": "2026-03-28T12:30:00Z", "end": "2026-03-28T13:00:00Z"},
            {"id": "a29", "title": "a29", "allDay": True, "startDate": "2026-03-29", "endDate": "2026-03-30"},
            {"id": "t28_2300", "title": "t", "allDay": False,
             "start": "2026-03-28T10:00:00Z", "end": "2026-03-28T10:30:00Z"},
        ]),
        # A timed event at exactly local midnight ties the all-day item: all-day first.
        "midnight_london": ("Europe/London", [
            {"id": "t_midnight", "title": "t", "allDay": False,
             "start": "2026-03-29T00:00:00Z", "end": "2026-03-29T00:30:00Z"},
            {"id": "a29", "title": "a29", "allDay": True, "startDate": "2026-03-29", "endDate": "2026-03-30"},
        ]),
        "midnight_auckland": ("Pacific/Auckland", [
            {"id": "t_midnight", "title": "t", "allDay": False,
             "start": "2026-03-28T11:00:00Z", "end": "2026-03-28T11:30:00Z"},
            {"id": "a29", "title": "a29", "allDay": True, "startDate": "2026-03-29", "endDate": "2026-03-30"},
        ]),
        # Exact ties keep input order (stable, like Python's sorted()).
        "ties": ("Europe/London", [
            {"id": "a1", "title": "a1", "allDay": True, "startDate": "2026-03-29", "endDate": "2026-03-30"},
            {"id": "t1", "title": "t1", "allDay": False,
             "start": "2026-03-29T09:00:00Z", "end": "2026-03-29T10:00:00Z"},
            {"id": "a2", "title": "a2", "allDay": True, "startDate": "2026-03-29", "endDate": "2026-03-31"},
            {"id": "t2", "title": "t2", "allDay": False,
             "start": "2026-03-29T10:00:00+01:00", "end": "2026-03-29T11:00:00+01:00"},
        ]),
        # London clocks go back at 01:00Z on 2026-10-25: 01:00-02:00 local happens twice.
        # Python compares same-zone datetimes by wall clock, so 01:15 GMT sorts
        # before 01:45 BST even though it is the later instant.
        "london_fold": ("Europe/London", [
            {"id": "bst_0145", "title": "t", "allDay": False,
             "start": "2026-10-25T00:45:00Z", "end": "2026-10-25T00:50:00Z"},
            {"id": "gmt_0115", "title": "t", "allDay": False,
             "start": "2026-10-25T01:15:00Z", "end": "2026-10-25T01:20:00Z"},
        ]),
    }

    EXPECTED_ORDER = {
        "check_d": ["late", "allday"],
        "london_dst": ["t28_2359", "a29", "t29_0030gmt", "t29_0230bst", "a30", "t30_0030bst"],
        "auckland": ["t28_2300", "a29", "t29_0130"],
        "midnight_london": ["a29", "t_midnight"],
        "midnight_auckland": ["a29", "t_midnight"],
        "ties": ["a1", "a2", "t1", "t2"],
        "london_fold": ["gmt_0115", "bst_0145"],
    }

    def _node_json(self, body, browser_tz):
        env = dict(os.environ, TZ=browser_tz)
        proc = subprocess.run(
            [NODE, "-e", JS_PREAMBLE + body, str(CARDS_JS)],
            cwd=str(REPO), capture_output=True, text=True, env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        return json.loads(proc.stdout)

    def _sorted_ids_in(self, browser_tz):
        """Sort every fixture via panelView (the board path) and sortCalendarItems."""
        body = r"""
const fixtures = %s;
const out = {browserOffset: new Date("2026-03-29T12:00:00Z").getTimezoneOffset()};
for (const name of Object.keys(fixtures)) {
  const [tz, items] = fixtures[name];
  const direct = BC.sortCalendarItems(items, tz).map((i) => i.id);
  // panelView shows CAL_LIMIT rows; page through by removing shown ids.
  const titled = items.map((i) => Object.assign({}, i, {title: i.id}));
  const shown = [];
  let rest = titled;
  while (rest.length) {
    const view = BC.panelView({
      id:"calendar", status:"ready", attemptedAt:"2026-03-29T12:00:00Z",
      updatedAt:"2026-03-29T12:00:00Z", totalCount:rest.length, timezone:tz,
      range:{start:"2026-03-28", end:"2026-04-01"}, items:rest,
    }, {});
    const ids = view.items.map((v) => v.title);
    shown.push(...ids);
    rest = rest.filter((i) => ids.indexOf(i.id) === -1);
  }
  out[name] = {direct, panel: shown};
}
console.log(JSON.stringify(out));
""" % json.dumps(self.SORT_FIXTURES)
        return self._node_json(body, browser_tz)

    def test_calendar_order_same_in_every_browser_timezone(self):
        runs = {tz: self._sorted_ids_in(tz) for tz in self.BROWSER_ZONES}
        offsets = {runs[tz]["browserOffset"] for tz in self.BROWSER_ZONES}
        self.assertEqual(len(offsets), 3, "TZ env did not change node's local zone")
        for name, want in self.EXPECTED_ORDER.items():
            for tz in self.BROWSER_ZONES:
                with self.subTest(fixture=name, browser=tz):
                    self.assertEqual(runs[tz][name]["direct"], want)
                    self.assertEqual(runs[tz][name]["panel"], want)

    def test_check_d_fixture_late_28th_before_all_day_29th(self):
        for tz in self.BROWSER_ZONES:
            with self.subTest(browser=tz):
                self.assertEqual(self._sorted_ids_in(tz)["check_d"]["panel"], ["late", "allday"])

    def test_calendar_order_matches_python_reference_sort(self):
        # Ties the browser rule to gws_cards._item_sort_key (code-review finding 2).
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        import gws_cards
        runs = {tz: self._sorted_ids_in(tz) for tz in self.BROWSER_ZONES}
        for name, (zone, items) in self.SORT_FIXTURES.items():
            py_ids = [i["id"] for i in sorted(
                items, key=lambda it: gws_cards._item_sort_key(it, zone))]
            with self.subTest(fixture=name):
                self.assertEqual(py_ids, self.EXPECTED_ORDER[name])
                for tz in self.BROWSER_ZONES:
                    self.assertEqual(runs[tz][name]["direct"], py_ids, tz)

    def test_calendar_sort_missing_or_invalid_timezone_falls_back_to_utc(self):
        body = r"""
const items = [
  {id:"a29", title:"a29", allDay:true, startDate:"2026-03-29", endDate:"2026-03-30"},
  {id:"t29_0030z", title:"t29_0030z", allDay:false, start:"2026-03-29T00:30:00Z", end:"2026-03-29T01:00:00Z"},
  {id:"t28_2330z", title:"t28_2330z", allDay:false, start:"2026-03-28T23:30:00Z", end:"2026-03-28T23:50:00Z"},
];
const ids = (xs) => xs.map((i) => i.id);
const out = {};
out.noArg = ids(BC.sortCalendarItems(items));
out.undef = ids(BC.sortCalendarItems(items, undefined));
out.empty = ids(BC.sortCalendarItems(items, ""));
out.invalid = ids(BC.sortCalendarItems(items, "Not/A_Zone"));
out.garbage = ids(BC.sortCalendarItems(items, "]]bad zone[["));
const card = (tz) => ({
  id:"calendar", status:"ready", attemptedAt:"2026-03-29T12:00:00Z",
  updatedAt:"2026-03-29T12:00:00Z", totalCount:3, timezone:tz,
  range:{start:"2026-03-28", end:"2026-03-30"}, items,
});
const noTz = card(undefined); delete noTz.timezone;
out.panelMissing = BC.panelView(noTz, {}).items.map((i) => i.title);
out.panelInvalid = BC.panelView(card("Bogus/Zone"), {}).items.map((i) => i.title);
out.panelInvalidMode = BC.panelView(card("Bogus/Zone"), {}).mode;
// Unparsable or missing dates must not throw either.
const odd = [
  {id:"ok", allDay:false, start:"2026-03-29T09:00:00Z"},
  {id:"badstart", allDay:false, start:"not a date"},
  {id:"nostart", allDay:false},
  {id:"badday", allDay:true, startDate:"soon"},
  {id:"noday", allDay:true},
];
out.odd = ids(BC.sortCalendarItems(odd, "Europe/London"));
out.oddInvalidTz = ids(BC.sortCalendarItems(odd, "Nope/Nope"));
out.notArray = BC.sortCalendarItems(null, "Europe/London").length;
console.log(JSON.stringify(out));
"""
        utc = ["t28_2330z", "a29", "t29_0030z"]
        for tz in self.BROWSER_ZONES:
            with self.subTest(browser=tz):
                out = self._node_json(body, tz)
                for key in ("noArg", "undef", "empty", "invalid", "garbage",
                            "panelMissing", "panelInvalid"):
                    self.assertEqual(out[key], utc, key)
                self.assertEqual(out["panelInvalidMode"], "ready")
                self.assertEqual(sorted(out["odd"]), sorted(["ok", "badstart", "nostart", "badday", "noday"]))
                self.assertEqual(out["odd"][-1], "ok", "dateless items sort first, valid one last")
                self.assertEqual(out["oddInvalidTz"], out["odd"])
                self.assertEqual(out["notArray"], 0)

    def test_sort_path_reads_no_browser_local_time(self):
        js = CARDS_JS.read_text()
        start = js.find("const zoneFormatters")
        end = js.find("function ymdToUTC")
        self.assertGreater(start, 0)
        self.assertGreater(end, start)
        sort_path = js[start:end]
        for getter in ("getFullYear", "getMonth", "getDate", "getHours",
                       "getMinutes", "getTimezoneOffset", "getDay", "localYMD"):
            self.assertNotIn(getter + "(", sort_path, getter)
        self.assertIn("sortCalendarItems(items, card.timezone)", js)

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
