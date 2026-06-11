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

  function isVisible(el) {
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return false;
    const style = window.getComputedStyle(el);
    if (style.visibility === "hidden" || style.display === "none" || style.opacity === "0") {
      return false;
    }
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
      disabled: !!el.disabled,
      bbox: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
    };
  }

  window.__agentCollect = function () {
    const nodes = Array.from(document.querySelectorAll(SELECTOR));
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
})();
