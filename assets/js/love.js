(function () {
  const page = document.querySelector(".love-page[data-love-start]");
  if (!page) return;

  const includeStartDay = true;
  const startDate = new Date(page.dataset.loveStart);
  if (Number.isNaN(startDate.getTime())) return;

  const startDay = new Date(startDate.getFullYear(), startDate.getMonth(), startDate.getDate());

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

  function updateTimelineDayLabels() {
    document.querySelectorAll(".timeline-item[data-date]").forEach((item) => {
      const label = item.querySelector(".timeline-since");
      const itemDate = parseTimelineDate(item.dataset.date || "");
      if (!label || !itemDate) return;

      const diff = dayDifference(itemDate, startDay);
      label.textContent = diff < 0
        ? `${Math.abs(diff)} days before together`
        : `Day ${diff + (includeStartDay ? 1 : 0)} together`;
    });
  }

  updateLoveTime();
  updateTimelineDayLabels();
  setInterval(updateLoveTime, 1000);
}());
