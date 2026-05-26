(function () {
  const page = document.querySelector(".love-page[data-love-music-src]");
  const container = document.getElementById("love-aplayer");
  if (!page || !container) return;

  function playWhenAllowed(player) {
    const play = () => {
      const result = player.play();
      if (result && typeof result.catch === "function") {
        result.catch(() => {});
      }
    };

    window.setTimeout(play, 800);
    ["pointerdown", "keydown", "touchstart"].forEach((eventName) => {
      window.addEventListener(eventName, play, { once: true, passive: true });
    });
  }

  function initPlayer(audio) {
    if (!window.APlayer || !Array.isArray(audio) || audio.length === 0) return;

    const player = new window.APlayer({
      container,
      fixed: true,
      mini: true,
      autoplay: true,
      theme: "#f2a7bd",
      loop: "all",
      order: "list",
      preload: "metadata",
      volume: 0.52,
      mutex: true,
      listFolded: true,
      listMaxHeight: "280px",
      lrcType: 0,
      audio,
    });

    playWhenAllowed(player);
  }

  fetch(page.dataset.loveMusicSrc, { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error("Music list request failed.");
      return response.json();
    })
    .then(initPlayer)
    .catch(() => {});
}());
