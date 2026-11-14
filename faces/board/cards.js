/*
 * ai-visualizer: give your AI agent a face.
 * Copyright (C) 2026 Jared Rhodenizer
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as published
 * by the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */
/* Board info cards: poll GET /board-cards on its own timer, not the voice bus. */
(function (root) {
  "use strict";

  const TODO_LIMIT = 5;
  const CAL_LIMIT = 3;
  const POLL_MS = 2000;
  const BoardCards = {
    TODO_LIMIT: TODO_LIMIT,
    CAL_LIMIT: CAL_LIMIT,
    POLL_MS: POLL_MS,
    agentName: "JARVIS",
  };

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function formatHM(iso, timeZone) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const opts = { hour: "2-digit", minute: "2-digit", hourCycle: "h23" };
    if (timeZone) opts.timeZone = timeZone;
    const parts = new Intl.DateTimeFormat("en-GB", opts).formatToParts(d);
    let hour = "00", minute = "00";
    for (let i = 0; i < parts.length; i++) {
      if (parts[i].type === "hour") hour = pad2(parts[i].value);
      if (parts[i].type === "minute") minute = pad2(parts[i].value);
    }
    return hour + ":" + minute;
  }

  function formatUpdated(iso, timeZone) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    const opts = {
      year: "numeric", month: "short", day: "2-digit",
      hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    };
    if (timeZone) opts.timeZone = timeZone;
    return new Intl.DateTimeFormat("en-GB", opts).format(d);
  }

  // Calendar order mirrors gws_cards.py _item_sort_key: (start in the CARD's
  // zone, all-day first on a tie). Python compares those aware datetimes as
  // local wall-clock times (same tzinfo), and an all-day item starts at local
  // midnight of startDate. So the key here is the wall-clock "YYYY-MM-DDTHH:MM:SS.mmm"
  // in card.timezone; never the browser's own zone.
  const zoneFormatters = {};

  function zoneFormatter(tz) {
    const zone = tz ? String(tz) : "UTC";
    if (!zoneFormatters[zone]) {
      const opts = {
        year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
      };
      try {
        zoneFormatters[zone] = new Intl.DateTimeFormat("en-CA", Object.assign({ timeZone: zone }, opts));
      } catch (err) {
        // Missing or unknown zone (RangeError): fall back to UTC, never throw.
        zoneFormatters[zone] = zone === "UTC"
          ? null
          : zoneFormatter("UTC");
      }
    }
    return zoneFormatters[zone];
  }

  function wallClockKey(d, tz) {
    const fmt = zoneFormatter(tz);
    if (!fmt) return d.toISOString().slice(0, 23);
    const p = {};
    const parts = fmt.formatToParts(d);
    for (let i = 0; i < parts.length; i++) p[parts[i].type] = parts[i].value;
    return p.year + "-" + pad2(p.month) + "-" + pad2(p.day) + "T" +
      pad2(p.hour === "24" ? "00" : p.hour) + ":" + pad2(p.minute) + ":" + pad2(p.second) +
      "." + String(d.getUTCMilliseconds()).padStart(3, "0");
  }

  function calendarSortKey(item, tz) {
    if (!item) return "";
    if (item.allDay) {
      const s = String(item.startDate || "");
      return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s + "T00:00:00.000" : "";
    }
    const d = new Date(item.start);
    if (Number.isNaN(d.getTime())) return "";
    return wallClockKey(d, tz);
  }

  // tz is the card's own zone (card.timezone), optional; missing/invalid -> UTC.
  // Array.prototype.sort is stable, so exact ties keep input order (like sorted()).
  function sortCalendarItems(items, tz) {
    const keyed = (Array.isArray(items) ? items : []).map(function (item) {
      return { item: item, key: calendarSortKey(item, tz), allDay: !!(item && item.allDay) };
    });
    keyed.sort(function (a, b) {
      if (a.key < b.key) return -1;
      if (a.key > b.key) return 1;
      if (a.allDay && !b.allDay) return -1;
      if (!a.allDay && b.allDay) return 1;
      return 0;
    });
    return keyed.map(function (k) { return k.item; });
  }

  function ymdToUTC(s) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s || ""));
    return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) : NaN;
  }

  // Stored all-day items carry an EXCLUSIVE endDate (Google style), so the
  // last day of a multi-day event is endDate - 1. Returns "" for a one-day
  // event (endDate = startDate + 1) or when either date is missing or odd.
  function lastAllDay(item) {
    const start = ymdToUTC(item.startDate);
    const end = ymdToUTC(item.endDate);
    if (Number.isNaN(start) || Number.isNaN(end)) return "";
    const last = end - 86400000;
    return last > start ? new Date(last).toISOString().slice(0, 10) : "";
  }

  function presentItem(cardId, item, timeZone) {
    let meta = "";
    if (cardId === "todo") {
      meta = item.dueDate || "";
    } else if (item.allDay) {
      const last = lastAllDay(item);
      meta = "All day · " + (item.startDate || "") + (last ? " → " + last : "");
    } else {
      meta = formatHM(item.start, timeZone) + " – " + formatHM(item.end, timeZone);
    }
    return { id: item.id, title: item.title, meta: meta };
  }

  function emptyPanel(id, mode, statusText) {
    return {
      id: id, mode: mode, statusText: statusText, items: [], overflow: 0,
      rangeLabel: null, timezone: null, updatedLabel: null, message: null,
    };
  }

  function panelView(card, opts) {
    opts = opts || {};
    if (!card || card._missing || !card.status) {
      const id = card && card.id ? card.id : "todo";
      if (opts.connectionError) {
        return emptyPanel(id, "unavailable", "Board cards unavailable.");
      }
      const name = (opts.agentName || BoardCards.agentName || "JARVIS");
      const invite = id === "calendar"
        ? "Ask " + name + " for your calendar."
        : "Ask " + name + " for your tasks.";
      return emptyPanel(id, "invitation", invite);
    }
    const items = Array.isArray(card.items) ? card.items : [];
    const limit = card.id === "calendar" ? CAL_LIMIT : TODO_LIMIT;
    const ordered = card.id === "calendar" ? sortCalendarItems(items, card.timezone) : items.slice();
    const total = Math.max(Number(card.totalCount) || 0, ordered.length);
    const shown = ordered.slice(0, limit).map(function (it) {
      return presentItem(card.id, it, opts.timeZone);
    });
    const overflow = Math.max(0, total - shown.length);
    let mode = "ready";
    let statusText = "";
    if (card.status === "loading") {
      mode = "loading";
      statusText = items.length
        ? "Updating…"
        : (card.id === "calendar" ? "Fetching calendar…" : "Fetching tasks…");
    } else if (card.status === "error") {
      mode = "error";
      statusText = card.message || "Request failed.";
    } else if (card.status === "ready" && items.length === 0) {
      mode = "empty";
      statusText = card.id === "calendar" ? "No events in this range." : "No open tasks.";
    }
    const rangeLabel = card.range && card.range.start && card.range.end
      ? card.range.start + " → " + card.range.end
      : null;
    const view = {
      id: card.id,
      mode: mode,
      statusText: statusText,
      items: shown,
      overflow: overflow,
      rangeLabel: rangeLabel,
      timezone: card.timezone || null,
      updatedLabel: card.updatedAt ? formatUpdated(card.updatedAt, opts.timeZone) : null,
      message: card.status === "error" ? (card.message || "") : null,
    };
    if (opts.connectionError) {
      view.mode = "unavailable";
      view.statusText = "Board cards unavailable.";
    }
    return view;
  }

  function findCard(cards, id) {
    if (!cards) return null;
    for (let i = 0; i < cards.length; i++) {
      if (cards[i] && cards[i].id === id) return cards[i];
    }
    return null;
  }

  function snapshotView(payload, opts) {
    opts = opts || {};
    const cards = payload && payload.cards ? payload.cards : [];
    return {
      todo: panelView(findCard(cards, "todo") || { id: "todo", _missing: true }, opts),
      calendar: panelView(findCard(cards, "calendar") || { id: "calendar", _missing: true }, opts),
    };
  }

  function shouldIgnoreGlobalKeys(target) {
    if (!target) return false;
    if (typeof target.closest === "function") {
      if (target.closest(".board-card")) return true;
      if (target.closest("input,textarea,select,button,a,[contenteditable='true'],[contenteditable],[role='textbox'],[role='button']")) {
        return true;
      }
    }
    const name = String(target.tagName || "").toUpperCase();
    if (name === "INPUT" || name === "TEXTAREA" || name === "SELECT" ||
        name === "BUTTON" || name === "A") return true;
    if (target.isContentEditable) return true;
    return false;
  }

  function createPoller(opts) {
    opts = opts || {};
    const intervalMs = opts.intervalMs || POLL_MS;
    const fetchFn = opts.fetchFn;
    const isHidden = opts.isHidden || function () { return false; };
    const setTimeoutFn = opts.setTimeoutFn || setTimeout;
    const clearTimeoutFn = opts.clearTimeoutFn || clearTimeout;
    let inFlight = false;
    let timer = null;
    let pendingImmediate = false;
    let stopped = false;

    function clearTimer() {
      if (timer != null) {
        clearTimeoutFn(timer);
        timer = null;
      }
    }

    function arm(ms) {
      clearTimer();
      timer = setTimeoutFn(function () {
        timer = null;
        kick();
      }, ms);
    }

    function kick() {
      if (stopped) return;
      if (isHidden()) return;
      if (inFlight) {
        pendingImmediate = true;
        return;
      }
      inFlight = true;
      let work;
      try {
        work = Promise.resolve(fetchFn());
      } catch (err) {
        work = Promise.reject(err);
      }
      work.then(function (result) {
          if (!stopped && opts.onPayload) opts.onPayload(result);
        })
        .catch(function (err) {
          if (!stopped && opts.onConnectionError) opts.onConnectionError(err);
        })
        .then(function () {
          inFlight = false;
          if (stopped) return;
          if (isHidden()) return;
          if (pendingImmediate) {
            pendingImmediate = false;
            kick();
          } else {
            arm(intervalMs);
          }
        });
    }

    return {
      start: kick,
      onVisibilityChange: function () {
        if (isHidden()) clearTimer();
        else kick();
      },
      stop: function () {
        stopped = true;
        clearTimer();
      },
    };
  }

  function setText(el, text) {
    if (!el) return;
    el.textContent = text == null ? "" : String(text);
  }

  function applyPanel(el, view) {
    if (!el) return;
    el.dataset.mode = view.mode;
    setText(el.querySelector("[data-role=status]"), view.statusText);
    const list = el.querySelector("[data-role=list]");
    if (list) {
      list.textContent = "";
      for (let i = 0; i < view.items.length; i++) {
        const item = view.items[i];
        const li = document.createElement("li");
        const title = document.createElement("div");
        title.className = "board-card-title";
        title.textContent = item.title;
        li.appendChild(title);
        if (item.meta) {
          const meta = document.createElement("div");
          meta.className = "board-card-item-meta";
          meta.textContent = item.meta;
          li.appendChild(meta);
        }
        list.appendChild(li);
      }
    }
    const bits = [];
    if (view.rangeLabel) bits.push(view.rangeLabel);
    if (view.timezone) bits.push(view.timezone);
    if (view.updatedLabel) bits.push("Updated " + view.updatedLabel);
    if (view.overflow) bits.push("+" + view.overflow + " more");
    setText(el.querySelector("[data-role=meta]"), bits.join(" · "));
  }

  function paint(view) {
    applyPanel(document.getElementById("card-todo"), view.todo);
    applyPanel(document.getElementById("card-calendar"), view.calendar);
  }

  function syncCine(root) {
    const cine = document.body.classList.contains("cine");
    root.inert = cine;
    root.setAttribute("aria-hidden", cine ? "true" : "false");
    const panels = root.querySelectorAll(".board-card");
    for (let i = 0; i < panels.length; i++) {
      panels[i].tabIndex = cine ? -1 : 0;
    }
  }

  const HUD_GAP = 16;
  const HUD_SELECTORS = ["#brand", "#statusblock"];

  // Pixels from the viewport top that the cards must start below so they
  // never cover the HUD. rects: DOMRect-like {bottom, width, height}.
  function hudClearance(rects, gap) {
    if (gap == null) gap = HUD_GAP;
    let bottom = 0;
    for (let i = 0; i < (rects || []).length; i++) {
      const r = rects[i];
      if (!r || !(r.width > 0 || r.height > 0)) continue;
      const b = Number(r.bottom);
      if (Number.isFinite(b) && b > bottom) bottom = b;
    }
    return bottom > 0 ? Math.ceil(bottom + gap) : 0;
  }

  function watchHud(root) {
    const els = [];
    for (let i = 0; i < HUD_SELECTORS.length; i++) {
      const el = document.querySelector(HUD_SELECTORS[i]);
      if (el) els.push(el);
    }
    if (!els.length || !root.style) return;
    let last = null;
    function update() {
      const px = hudClearance(els.map(function (el) { return el.getBoundingClientRect(); }));
      if (!px || px === last) return;
      last = px;
      root.style.setProperty("--hud-clear", px + "px");
    }
    update();
    if (typeof ResizeObserver === "function") {
      const ro = new ResizeObserver(update);
      els.forEach(function (el) { ro.observe(el); });
    }
    if (typeof window !== "undefined" && window.addEventListener) {
      window.addEventListener("resize", update);
    }
  }

  // The narrow layout caps #echo at 3 lines with overflow hidden (cards.css),
  // so keep the box scrolled to its end: the oldest lines are the ones that
  // drop out of view and the newest words and the blinking cursor stay shown.
  // A no-op where #echo does not overflow (wide layout) or is missing.
  function pinToEnd(el) {
    if (!el || typeof el.scrollHeight !== "number") return;
    el.scrollTop = el.scrollHeight;
  }

  // Ctor is injectable for tests; defaults to the page's MutationObserver.
  function watchTranscript(el, Ctor) {
    if (!el) return;
    if (!Ctor && typeof MutationObserver === "function") Ctor = MutationObserver;
    pinToEnd(el);
    if (Ctor) {
      new Ctor(function () { pinToEnd(el); }).observe(el, {
        childList: true, characterData: true, subtree: true,
      });
    }
    if (typeof window !== "undefined" && window.addEventListener) {
      window.addEventListener("resize", function () { pinToEnd(el); });
    }
  }

  function viewOpts(extra) {
    extra = extra || {};
    extra.agentName = BoardCards.agentName || "JARVIS";
    return extra;
  }

  function startLive() {
    let lastGood = { version: 1, cards: [] };
    const poller = createPoller({
      intervalMs: POLL_MS,
      isHidden: function () { return document.visibilityState === "hidden"; },
      fetchFn: function () {
        return fetch("/board-cards", { cache: "no-store" }).then(function (r) {
          if (r.status === 503 || !r.ok) {
            const err = new Error("unavailable");
            err.status = r.status;
            throw err;
          }
          return r.json();
        }).then(function (body) {
          if (!body || body.version !== 1 || !Array.isArray(body.cards)) {
            throw new Error("bad payload");
          }
          return body;
        });
      },
      onPayload: function (body) {
        lastGood = body;
        paint(snapshotView(body, viewOpts()));
      },
      onConnectionError: function () {
        paint(snapshotView(lastGood, viewOpts({ connectionError: true })));
      },
    });
    document.addEventListener("visibilitychange", function () {
      poller.onVisibilityChange();
    });
    poller.start();
  }

  function applyAgentName(name) {
    const trimmed = String(name || "").trim();
    if (trimmed) BoardCards.agentName = trimmed;
  }

  function init() {
    const root = document.getElementById("board-cards");
    if (!root) return;
    paint(snapshotView({ version: 1, cards: [] }, viewOpts()));
    if (typeof AV !== "undefined" && AV.ready) {
      AV.ready(function (a) {
        applyAgentName(a && a.name);
        ["todo", "calendar"].forEach(function (id) {
          const el = document.getElementById("card-" + id);
          if (el && el.dataset.mode === "invitation") {
            const status = el.querySelector("[data-role=status]");
            if (status) {
              status.textContent = id === "calendar"
                ? "Ask " + BoardCards.agentName + " for your calendar."
                : "Ask " + BoardCards.agentName + " for your tasks.";
            }
          }
        });
      });
    }
    if (typeof MutationObserver === "function") {
      const obs = new MutationObserver(function () { syncCine(root); });
      obs.observe(document.body, { attributes: true, attributeFilter: ["class"] });
    }
    syncCine(root);
    watchHud(root);
    watchTranscript(document.getElementById("echo"));
    startLive();
  }

  BoardCards.formatHM = formatHM;
  BoardCards.formatUpdated = formatUpdated;
  BoardCards.sortCalendarItems = sortCalendarItems;
  BoardCards.panelView = panelView;
  BoardCards.snapshotView = snapshotView;
  BoardCards.shouldIgnoreGlobalKeys = shouldIgnoreGlobalKeys;
  BoardCards.createPoller = createPoller;
  BoardCards.hudClearance = hudClearance;
  BoardCards.pinToEnd = pinToEnd;
  BoardCards.watchTranscript = watchTranscript;
  BoardCards.init = init;

  root.BoardCards = BoardCards;

  if (typeof document !== "undefined" && document.getElementById) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }
  }
})(typeof window !== "undefined" ? window : (typeof globalThis !== "undefined" ? globalThis : this));
