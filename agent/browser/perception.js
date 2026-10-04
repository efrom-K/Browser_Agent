// Injected into the page to find interactive elements, label them with
// numeric IDs and draw visual "set-of-marks" overlays for screenshots.
//
// The agent never relies on hardcoded selectors: every step this script
// re-scans the live DOM and assigns fresh IDs, which `actions.py` then maps
// back to real DOM nodes via `window.__agentElements`.
(() => {
  const SELECTOR = [
    "a[href]",
    "button",
    "input",
    "textarea",
    "select",
    "[role='button']",
    "[role='link']",
    "[role='checkbox']",
    "[role='radio']",
    "[role='tab']",
    "[role='menuitem']",
    "[role='combobox']",
    "[role='option']",
    "[role='switch']",
    "[role='slider']",
    "[contenteditable='true']",
    "[onclick]",
    "[tabindex]",
  ].join(",");

  // querySelectorAll that also searches open shadow roots (web components:
  // search dialogs, custom inputs...), which plain document queries miss.
  function deepQueryAll(selector, root = document) {
    const found = Array.from(root.querySelectorAll(selector));
    for (const el of root.querySelectorAll("*")) {
      if (el.shadowRoot) found.push(...deepQueryAll(selector, el.shadowRoot));
    }
    return found;
  }

  function isRendered(el) {
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return false;
    const style = window.getComputedStyle(el);
    return !(style.visibility === "hidden" || style.display === "none" || style.opacity === "0");
  }

  function isVisible(el) {
    if (!isRendered(el)) return false;
    const rect = el.getBoundingClientRect();
    if (rect.bottom < 0 || rect.top > window.innerHeight) return false;
    if (rect.right < 0 || rect.left > window.innerWidth) return false;
    return true;
  }

  function accessibleName(el) {
    const aria = el.getAttribute("aria-label");
    if (aria) return aria.trim();

    if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
      const placeholder = el.getAttribute("placeholder");
      if (placeholder) return placeholder.trim();
      if (el.value) return String(el.value).trim();
    }

    const text = (el.innerText || el.textContent || "").trim().replace(/\s+/g, " ");
    if (text) return text.slice(0, 80);

    const title = el.getAttribute("title");
    if (title) return title.trim();

    const alt = el.getAttribute("alt");
    if (alt) return alt.trim();

    return "";
  }

  function describe(el) {
    const rect = el.getBoundingClientRect();
    return {
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute("role") || "",
      type: el.getAttribute("type") || "",
      name: accessibleName(el),
      href: el.tagName === "A" ? el.getAttribute("href") || "" : "",
      disabled: !!el.disabled,
      bbox: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
    };
  }

  // "Next results page" controls (HN "More", Avito "Следующая страница",
  // "next ›"...). A lone "Ещё"/"More" menu button is too ambiguous on
  // Russian sites, so only "more" in English counts.
  const NEXT_RE = /^(next|next page|more|show more|load more|older posts|следующая|следующая страница|далее|вперёд|вперед|показать ещё|показать еще|›|»|→|>|>>)$/i;

  function isNextPage(el) {
    if (!["A", "BUTTON"].includes(el.tagName)) return false;
    if ((el.getAttribute("rel") || "").split(/\s+/).includes("next")) return true;
    const name = (accessibleName(el) || el.innerText || "").replace(/\s+/g, " ").trim();
    return NEXT_RE.test(name) || NEXT_RE.test(name.replace(/[\s›»→>]+$/, ""));
  }

  // The site's search field: small models otherwise wander through
  // categories instead of searching.
  function isSearchBox(el) {
    const role = el.getAttribute("role") || "";
    const type = (el.getAttribute("type") || "text").toLowerCase();
    if (!(el.tagName === "INPUT" && ["text", "search"].includes(type)) && role !== "searchbox") return false;
    if (type === "search" || role === "searchbox" || el.closest("[role=search]")) return true;
    const hints = [el.name, el.id, el.placeholder, el.getAttribute("aria-label")].join(" ");
    return /search|query|поиск|найти|искать/i.test(hints) || el.name === "q";
  }

  window.__agentCollect = function () {
    const nodes = deepQueryAll(SELECTOR);
    const seen = new Set();
    const elements = [];
    const descriptors = [];

    for (const el of nodes) {
      if (seen.has(el)) continue;
      if (!isVisible(el)) continue;
      seen.add(el);
      elements.push(el);
      descriptors.push(describe(el));
    }

    // The next-page control is usually far below the fold; list it anyway
    // (clicks scroll elements into view) so the agent needn't hunt for it.
    let next = elements.findIndex(isNextPage);
    if (next < 0) {
      const el = nodes.find((n) => !seen.has(n) && isRendered(n) && isNextPage(n));
      if (el) {
        elements.push(el);
        descriptors.push(describe(el));
        next = elements.length - 1;
      }
    }
    if (next >= 0) descriptors[next].next_page = true;
    const search = elements.findIndex(isSearchBox);
    if (search >= 0) descriptors[search].search_box = true;
    // Some layouts keep the pagination only in a hidden (e.g. other-breakpoint)
    // copy - then hand over its link for navigate instead.
    const hidden = next < 0 && nodes.find((n) => n.tagName === "A" && n.getAttribute("href") && isNextPage(n));
    window.__agentNextHref = hidden ? new URL(shortHref(hidden.getAttribute("href")), location.href).href : "";

    window.__agentElements = elements;
    return descriptors;
  };

  window.__agentShowMarks = function () {
    window.__agentRemoveMarks();

    const container = document.createElement("div");
    container.id = "__agent_marks__";
    document.body.appendChild(container);

    (window.__agentElements || []).forEach((el, i) => {
      const rect = el.getBoundingClientRect();

      const box = document.createElement("div");
      box.style.position = "fixed";
      box.style.left = rect.x + "px";
      box.style.top = rect.y + "px";
      box.style.width = rect.width + "px";
      box.style.height = rect.height + "px";
      box.style.border = "2px solid #ff3366";
      box.style.pointerEvents = "none";
      box.style.boxSizing = "border-box";
      box.style.zIndex = "2147483647";

      const label = document.createElement("div");
      label.textContent = String(i);
      label.style.position = "absolute";
      label.style.top = "-10px";
      label.style.left = "-2px";
      label.style.background = "#ff3366";
      label.style.color = "#fff";
      label.style.font = "bold 11px monospace";
      label.style.padding = "0 3px";
      label.style.lineHeight = "14px";
      label.style.borderRadius = "2px";

      box.appendChild(label);
      container.appendChild(box);
    });
  };

  window.__agentRemoveMarks = function () {
    const existing = document.getElementById("__agent_marks__");
    if (existing) existing.remove();
  };

  // Find the page's main repeated item list (search results, listings,
  // product cards...) without site knowledge: the largest group of sibling
  // elements sharing tag+class where each one contains a link and some text.
  // Returns one compact line per item: its short text facts + main link.
  function findItems() {
    let best = [];
    let bestScore = 0;
    for (const parent of document.querySelectorAll("body *")) {
      if (parent.children.length < 4) continue;
      const groups = new Map();
      for (const child of parent.children) {
        const key = child.tagName + "." + child.className;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(child);
      }
      for (const group of groups.values()) {
        if (group.length < 4) continue;
        const items = group.filter(
          (el) => el.querySelector("a[href]") && (el.innerText || "").trim().length > 15
        );
        if (items.length < 4) continue;
        const score = items.reduce((n, el) => n + Math.min(el.innerText.length, 600), 0);
        if (score > bestScore) {
          bestScore = score;
          best = items;
        }
      }
    }
    // An item can span several sibling rows (e.g. a table: title row + a
    // "points / comments" row): attach up to 2 following same-tag siblings
    // that aren't items themselves.
    const members = new Set(best);
    return best.map((el) => {
      const nodes = [el];
      let next = el.nextElementSibling;
      while (next && !members.has(next) && next.tagName === el.tagName && nodes.length < 3) {
        nodes.push(next);
        next = next.nextElementSibling;
      }
      return nodes;
    });
  }

  // Long query params are tracking noise (context=H4sI...), short ones are
  // often the identity (item?id=123, p=2) - keep only the short ones.
  function shortHref(href) {
    const [path, query] = href.split("?");
    const kept = (query || "").split("&").filter((p) => p && p.length <= 40);
    return kept.length ? path + "?" + kept.join("&") : path;
  }

  function itemLine(nodes) {
    const all = (sel) => nodes.flatMap((n) => Array.from(n.querySelectorAll(sel)));
    const text = (el) => (el.innerText || "").trim();
    // Main link: the href repeated most in the item (photo + title usually
    // both point to it); ties go to the link with the longest caption.
    const links = all("a[href]");
    const hrefOf = (a) => shortHref(a.getAttribute("href"));
    const counts = new Map();
    const longest = new Map();
    for (const a of links) {
      const h = hrefOf(a);
      counts.set(h, (counts.get(h) || 0) + 1);
      longest.set(h, Math.max(longest.get(h) || 0, text(a).length));
    }
    // A link in/around a heading is the item's title link (GitHub, Avito,
    // shops); otherwise the most repeated href (photo + title), ties to the
    // first one with a real caption (table rows: the name comes first).
    const H = "h1,h2,h3,h4,h5,h6";
    const headed = links.find((a) => a.closest(H) || a.querySelector(H));
    let href = headed ? hrefOf(headed) : "";
    for (const h of headed ? [] : counts.keys()) {
      if (longest.get(h) < 3 && counts.size > 1) continue;
      if (!href || counts.get(h) > counts.get(href)) href = h;
    }
    if (!href && counts.size) href = counts.keys().next().value;

    // Drop UI captions: buttons ("Show phone"), and short secondary links
    // without digits ("Write", "hide") - "99 comments" or "3 photos" stay.
    const mainLinks = links.filter((a) => hrefOf(a) === href);
    const title = mainLinks.reduce((t, a) => (text(a).length > text(t).length ? a : t), mainLinks[0]);
    const skip = new Set();
    for (const c of all("button, a[href]")) {
      if (c === title || (c.tagName === "A" && hrefOf(c) === href)) continue;
      const t = text(c);
      if (t.length < 25 && (c.tagName === "BUTTON" || !/\d/.test(t))) {
        t.split("\n").forEach((l) => skip.add(l.replace(/\s+/g, " ").trim()));
      }
    }
    for (const a of mainLinks) {
      if (a !== title && text(a).length < 25) text(a).split("\n").forEach((l) => skip.add(l.replace(/\s+/g, " ").trim()));
    }
    // Long lines are descriptions: keep a short hint of the first, drop the rest.
    const lines = [];
    let sawLong = false;
    for (const node of nodes) {
      for (let line of text(node).split("\n")) {
        line = line.replace(/\s+/g, " ").trim();
        if (line.length < 2 || skip.has(line) || lines.includes(line)) continue;
        if (line.length > 80) {
          if (sawLong) continue;
          sawLong = true;
          line = line.slice(0, 60) + "…";
        }
        lines.push(line);
      }
    }
    return { lines, href };
  }

  window.__agentListCount = function () {
    return findItems().length;
  };

  window.__agentReadList = function () {
    const items = findItems().map(itemLine);
    // Lines shared by most items are boilerplate, not facts that tell them apart.
    const freq = new Map();
    for (const it of items) for (const l of it.lines) freq.set(l, (freq.get(l) || 0) + 1);
    const common = (l) => items.length >= 5 && freq.get(l) > items.length * 0.8;
    return items.map(
      (it) => it.lines.filter((l) => !common(l)).join(" | ") + (it.href ? " -> " + it.href : "")
    );
  };
})();
