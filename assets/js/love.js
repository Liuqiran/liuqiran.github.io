(function () {
  const page = document.querySelector(".love-page[data-love-start]");
  if (!page) return;

  const includeStartDay = true;
  const startDate = new Date(page.dataset.loveStart);
  if (Number.isNaN(startDate.getTime())) return;

  const startDay = new Date(startDate.getFullYear(), startDate.getMonth(), startDate.getDate());
  let loveSearchItems = [];
  let selectTimelineYear = null;

  function setText(id, value, pad) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = pad ? String(value).padStart(2, "0") : String(value);
  }

  function dayDifference(a, b) {
    const da = new Date(a.getFullYear(), a.getMonth(), a.getDate());
    const db = new Date(b.getFullYear(), b.getMonth(), b.getDate());
    return Math.round((da - db) / 86400000);
  }

  function exactDuration(start, end) {
    let years = end.getFullYear() - start.getFullYear();
    let months = end.getMonth() - start.getMonth();
    let days = end.getDate() - start.getDate();
    let hours = end.getHours() - start.getHours();
    let minutes = end.getMinutes() - start.getMinutes();
    let seconds = end.getSeconds() - start.getSeconds();

    if (seconds < 0) {
      minutes -= 1;
      seconds += 60;
    }
    if (minutes < 0) {
      hours -= 1;
      minutes += 60;
    }
    if (hours < 0) {
      days -= 1;
      hours += 24;
    }
    if (days < 0) {
      months -= 1;
      days += new Date(end.getFullYear(), end.getMonth(), 0).getDate();
    }
    if (months < 0) {
      years -= 1;
      months += 12;
    }

    return { years, months, days, hours, minutes, seconds };
  }

  function parseTimelineDate(value) {
    const parts = value.split("-").map(Number);
    if (parts.length !== 3 || parts.some(Number.isNaN)) return null;
    return new Date(parts[0], parts[1] - 1, parts[2]);
  }

  function updateLoveTime() {
    const now = new Date();
    const duration = exactDuration(startDate, now);
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const totalDays = dayDifference(today, startDay) + (includeStartDay ? 1 : 0);

    setText("total-days", totalDays, false);
    setText("live-years", duration.years, false);
    setText("live-months", duration.months, false);
    setText("live-days", duration.days, false);
    setText("live-hours", duration.hours, true);
    setText("live-minutes", duration.minutes, true);
    setText("live-seconds", duration.seconds, true);
  }

  function updateTimelineDayLabels(root) {
    const scope = root || document;
    scope.querySelectorAll(".timeline-item[data-date]").forEach((item) => {
      const label = item.querySelector(".timeline-since");
      const itemDate = parseTimelineDate(item.dataset.date || "");
      if (!label || !itemDate) return;

      const diff = dayDifference(itemDate, startDay);
      label.textContent = diff < 0
        ? `${Math.abs(diff)} days before together`
        : `Day ${diff + (includeStartDay ? 1 : 0)} together`;
    });
  }

  function prepareLoveImages(root) {
    const scope = root || document;
    scope.querySelectorAll(".timeline-media img, .love-post-content img").forEach((img) => {
      img.tabIndex = 0;
      img.setAttribute("role", "button");
      img.setAttribute("aria-label", img.alt ? `Open image: ${img.alt}` : "Open image");
    });
  }

  function setupLoveImageViewer() {
    const viewer = document.createElement("div");
    viewer.className = "love-image-viewer";
    viewer.hidden = true;
    viewer.innerHTML = '<button class="love-image-close" type="button" aria-label="Close image">&times;</button><img alt="">';
    document.body.appendChild(viewer);

    const viewerImage = viewer.querySelector("img");
    const closeButton = viewer.querySelector(".love-image-close");
    let closeTimer = 0;

    function closeViewer() {
      if (viewer.hidden) return;
      window.clearTimeout(closeTimer);
      viewer.classList.remove("is-open");
      document.documentElement.classList.remove("love-lightbox-open");
      closeTimer = window.setTimeout(() => {
        viewer.hidden = true;
        if (viewerImage) {
          viewerImage.removeAttribute("src");
          viewerImage.alt = "";
        }
      }, 340);
    }

    function openViewer(img) {
      if (!viewerImage || !img.currentSrc && !img.src) return;
      window.clearTimeout(closeTimer);
      viewerImage.src = img.currentSrc || img.src;
      viewerImage.alt = img.alt || "";
      document.documentElement.classList.add("love-lightbox-open");
      viewer.hidden = false;
      requestAnimationFrame(() => viewer.classList.add("is-open"));
      if (closeButton) closeButton.focus();
    }

    page.addEventListener("click", (event) => {
      const img = event.target.closest(".timeline-media img, .love-post-content img");
      if (img) openViewer(img);
    });

    page.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const img = event.target.closest(".timeline-media img, .love-post-content img");
      if (!img) return;
      event.preventDefault();
      openViewer(img);
    });

    viewer.addEventListener("click", (event) => {
      if (event.target === viewer || event.target === closeButton) closeViewer();
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !viewer.hidden) closeViewer();
    });
  }

  function setupTimelineYears() {
    const buttons = Array.from(document.querySelectorAll("[data-timeline-year-button]"));
    const panels = Array.from(document.querySelectorAll("[data-timeline-year-panel]"));
    if (!buttons.length || !panels.length) return;

    function loadYearPanel(panel, year) {
      if (panel.dataset.timelineLoaded === "true") return;
      const template = document.querySelector(`[data-timeline-year-template="${year}"]`);
      if (!template) return;
      panel.appendChild(template.content.cloneNode(true));
      panel.dataset.timelineLoaded = "true";
      prepareLoveImages(panel);
    }

    function selectYear(year) {
      buttons.forEach((button) => {
        const active = button.dataset.timelineYearButton === year;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      });

      panels.forEach((panel) => {
        const active = panel.dataset.timelineYearPanel === year;
        if (active) loadYearPanel(panel, year);
        panel.classList.toggle("is-active", active);
        panel.hidden = !active;
        if (active) updateTimelineDayLabels(panel);
      });
    }

    buttons.forEach((button) => {
      button.addEventListener("click", () => selectYear(button.dataset.timelineYearButton));
    });

    selectTimelineYear = selectYear;
  }

  function normalizeSearchText(value) {
    return String(value || "").toLowerCase().trim();
  }

  function goToTimelineTarget(target, year, homeUrl) {
    if (!target) return false;

    if (selectTimelineYear && year) {
      selectTimelineYear(year);
    }

    window.setTimeout(() => {
      const item = document.getElementById(target);
      if (!item) {
        if (homeUrl) window.location.href = `${homeUrl}#${target}`;
        return;
      }

      item.classList.add("is-found");
      item.scrollIntoView({ behavior: "smooth", block: "center" });
      window.setTimeout(() => item.classList.remove("is-found"), 2200);
    }, 50);
    return true;
  }

  function setupLoveSearch() {
    const search = document.querySelector("[data-love-search]");
    const data = document.getElementById("love-search-data");
    if (!search || !data) {
      loveSearchItems = [];
      return;
    }

    const input = search.querySelector("#love-search-input");
    const results = search.querySelector("[data-love-search-results]");
    const status = search.querySelector("[data-love-search-status]");
    const clearButton = search.querySelector("[data-love-search-clear]");
    const homeUrl = search.dataset.loveHome || "/";
    if (!input || !results) return;

    try {
      loveSearchItems = JSON.parse(data.textContent || "[]");
    } catch (error) {
      loveSearchItems = [];
    }

    function scoreItem(item, query) {
      const title = normalizeSearchText(item.title);
      const date = normalizeSearchText(item.date);
      const content = normalizeSearchText(item.content);
      const label = normalizeSearchText(item.label);
      let score = 0;

      if (title === query) score += 90;
      if (title.includes(query)) score += 45;
      if (date.includes(query)) score += 30;
      if (label.includes(query)) score += 12;
      if (content.includes(query)) score += 18;
      return score;
    }

    function createResult(item) {
      const href = item.url || (item.target ? `${homeUrl}#${item.target}` : homeUrl);
      const result = document.createElement("a");
      result.className = "love-search-result";
      result.href = href;
      if (item.type === "timeline" && item.target) {
        result.dataset.timelineTarget = item.target;
        result.dataset.timelineYear = item.year || "";
      }

      const meta = document.createElement("span");
      meta.className = "love-search-result-meta";
      meta.textContent = [item.label, item.date].filter(Boolean).join(" · ");

      const title = document.createElement("strong");
      title.textContent = item.title || item.content || "Memory";

      result.append(meta, title);
      return result;
    }

    function render(query) {
      results.textContent = "";
      if (status) status.textContent = "";

      const normalized = normalizeSearchText(query);
      if (!normalized) return;

      const matches = loveSearchItems
        .map((item) => ({ item, score: scoreItem(item, normalized) }))
        .filter((match) => match.score > 0)
        .sort((a, b) => b.score - a.score)
        .slice(0, 10);

      if (status) status.textContent = matches.length ? `${matches.length} found` : "No memories found";
      matches.forEach((match) => results.appendChild(createResult(match.item)));
    }

    input.addEventListener("input", () => render(input.value));
    if (clearButton) {
      clearButton.addEventListener("click", () => {
        input.value = "";
        render("");
        input.focus();
      });
    }

    results.addEventListener("click", (event) => {
      const result = event.target.closest("[data-timeline-target]");
      if (!result) return;
      const handled = goToTimelineTarget(result.dataset.timelineTarget, result.dataset.timelineYear, homeUrl);
      if (handled) event.preventDefault();
    });
  }

  function setupTimelineHash() {
    const target = window.location.hash ? decodeURIComponent(window.location.hash.slice(1)) : "";
    if (!target || !target.startsWith("memory-")) return;
    const item = loveSearchItems.find((entry) => entry.target === target);
    goToTimelineTarget(target, item && item.year, null);
  }

  function setupDynamicContent() {
    updateLoveTime();
    updateTimelineDayLabels();
    prepareLoveImages();
    setupTimelineYears();
    setupLoveSearch();
    setupTimelineHash();
  }

  function setupLoveNavigation() {
    const lovePathPattern = /^\/(?:en\/)?our-garden-2025-0927-k8f3q9p2\//;

    function isInternalLoveUrl(url) {
      return url.origin === window.location.origin && lovePathPattern.test(url.pathname);
    }

    function replaceCardFromDocument(doc) {
      const nextPage = doc.querySelector(".love-page");
      const nextCard = doc.querySelector(".love-card");
      const currentCard = page.querySelector(".love-card");
      if (!nextPage || !nextCard || !currentCard) return false;

      page.className = nextPage.className;
      currentCard.replaceWith(nextCard);
      document.title = doc.title || document.title;
      setupDynamicContent();
      return true;
    }

    function navigate(url, pushState) {
      page.classList.add("is-navigating");
      fetch(url.href, { headers: { "X-Requested-With": "love-navigation" } })
        .then((response) => {
          if (!response.ok) throw new Error("Love page request failed.");
          return response.text();
        })
        .then((html) => {
          const doc = new DOMParser().parseFromString(html, "text/html");
          if (!replaceCardFromDocument(doc)) throw new Error("Love page content missing.");
          if (pushState) history.pushState({ love: true }, "", url.href);
          if (url.hash) {
            setupTimelineHash();
          } else {
            window.scrollTo({ top: 0, behavior: "smooth" });
          }
        })
        .catch(() => {
          window.location.href = url.href;
        })
        .finally(() => page.classList.remove("is-navigating"));
    }

    page.addEventListener("click", (event) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const anchor = event.target.closest("a[href]");
      if (!anchor || anchor.hasAttribute("download") || (anchor.target && anchor.target !== "_self")) return;

      const url = new URL(anchor.href, window.location.href);
      if (!isInternalLoveUrl(url)) return;
      if (url.pathname === window.location.pathname && url.search === window.location.search && url.hash) return;

      event.preventDefault();
      navigate(url, true);
    });

    window.addEventListener("popstate", () => {
      const url = new URL(window.location.href);
      if (isInternalLoveUrl(url)) navigate(url, false);
    });
  }

  function setupTopLink() {
    const topLink = document.getElementById("top-link");
    const readProgress = document.getElementById("read_progress");
    if (!topLink) return;

    function updateTopLink() {
      const scrollHeight = document.documentElement.scrollHeight;
      const clientHeight = document.documentElement.clientHeight;
      const scrollTop = document.documentElement.scrollTop || document.body.scrollTop;
      const scrollable = Math.max(1, scrollHeight - clientHeight);
      if (readProgress) {
        readProgress.textContent = Math.min(100, Math.round((scrollTop / scrollable) * 100));
      }

      const visible = scrollTop > 800;
      topLink.style.visibility = visible ? "visible" : "hidden";
      topLink.style.opacity = visible ? "1" : "0";
    }

    topLink.addEventListener("click", (event) => {
      event.preventDefault();
      const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({ top: 0, behavior: prefersReducedMotion ? "auto" : "smooth" });
      history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
    });

    document.addEventListener("scroll", updateTopLink, { passive: true });
    updateTopLink();
  }

  updateLoveTime();
  setupDynamicContent();
  setupLoveImageViewer();
  setupLoveNavigation();
  setupTopLink();
  setInterval(updateLoveTime, 1000);
}());
