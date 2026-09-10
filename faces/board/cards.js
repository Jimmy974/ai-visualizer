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

  function localYMD(d) {
    return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate());
  }

  function eventDay(item) {
    if (item.allDay) return item.startDate || "";
    const d = new Date(item.start);
    if (Number.isNaN(d.getTime())) return "";
    return localYMD(d);
  }

  function sortCalendarItems(items) {
    return items.slice().sort(function (a, b) {
      const da = eventDay(a), db = eventDay(b);
      if (da < db) return -1;
      if (da > db) return 1;
      if (a.allDay && !b.allDay) return -1;
      if (!a.allDay && b.allDay) return 1;
      if (!a.allDay && !b.allDay) {
        return new Date(a.start) - new Date(b.start);
      }
      return 0;
    });
  }

  function presentItem(cardId, item, timeZone) {
    let meta = "";
    if (cardId === "todo") {
      meta = item.dueDate || "";
    } else if (item.allDay) {
      meta = "All day · " + (item.startDate || "");
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
      const invite = id === "calendar"
        ? "Ask Sinner for your calendar."
        : "Ask Sinner for your tasks.";
      return emptyPanel(id, "invitation", invite);
    }
    const items = Array.isArray(card.items) ? card.items : [];
    const limit = card.id === "calendar" ? CAL_LIMIT : TODO_LIMIT;
    const ordered = card.id === "calendar" ? sortCalendarItems(items) : items.slice();
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
        paint(snapshotView(body, {}));
      },
      onConnectionError: function () {
        paint(snapshotView(lastGood, { connectionError: true }));
      },
    });
    document.addEventListener("visibilitychange", function () {
      poller.onVisibilityChange();
    });
    poller.start();
  }

  function init() {
    const root = document.getElementById("board-cards");
    if (!root) return;
    paint(snapshotView({ version: 1, cards: [] }, {}));
    if (typeof MutationObserver === "function") {
      const obs = new MutationObserver(function () { syncCine(root); });
      obs.observe(document.body, { attributes: true, attributeFilter: ["class"] });
    }
    syncCine(root);
    startLive();
  }

  BoardCards.formatHM = formatHM;
  BoardCards.formatUpdated = formatUpdated;
  BoardCards.sortCalendarItems = sortCalendarItems;
  BoardCards.panelView = panelView;
  BoardCards.snapshotView = snapshotView;
  BoardCards.shouldIgnoreGlobalKeys = shouldIgnoreGlobalKeys;
  BoardCards.createPoller = createPoller;
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
