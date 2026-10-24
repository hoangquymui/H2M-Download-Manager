/**
 * HDM Browser Extension - Floating Video Download Panel (IDM Style)
 * Automatically sniffs video elements on web pages & YouTube,
 * injecting an IDM-style floating download button over the video player.
 */

(function () {
  "use strict";

  // Prevent multiple injections in the same frame
  if (window.__HDM_CONTENT_SCRIPT_LOADED__) return;
  window.__HDM_CONTENT_SCRIPT_LOADED__ = true;

  const SVG_DOWNLOAD_ICON = `
    <svg viewBox="0 0 24 24">
      <path d="M12 4v11m-5-5 5 5 5-5M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2" />
    </svg>
  `;

  const SVG_ARROW_ICON = `
    <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="6 9 12 15 18 9"></polyline>
    </svg>
  `;

  // Detect whether current page is YouTube
  function isYouTube() {
    return window.location.hostname.includes("youtube.com") || window.location.hostname.includes("youtu.be");
  }

  // Get current video title
  function getVideoTitle() {
    if (isYouTube()) {
      const ytTitle = document.querySelector("h1.ytd-watch-metadata yt-formatted-string") ||
                      document.querySelector("#title h1 yt-formatted-string") ||
                      document.querySelector("h1.title");
      if (ytTitle && ytTitle.textContent.trim()) {
        return ytTitle.textContent.trim();
      }
      return document.title.replace(/ - YouTube$/, "").trim() || "YouTube Video";
    }

    const ogTitle = document.querySelector('meta[property="og:title"]');
    if (ogTitle && ogTitle.content) {
      return ogTitle.content.trim();
    }

    return document.title.trim() || "Video";
  }

  // Find the appropriate player container to anchor the panel
  function findAnchorContainer(video) {
    if (isYouTube()) {
      const ytPlayer = document.querySelector("#movie_player") ||
                       document.querySelector(".html5-video-player") ||
                       video.closest(".html5-video-player");
      if (ytPlayer) return ytPlayer;
    }

    // Generic sites: find a suitably sized parent container
    let container = video.parentElement;
    while (container && container !== document.body) {
      const style = window.getComputedStyle(container);
      if (container.offsetWidth >= 280 && container.offsetHeight >= 160) {
        return container;
      }
      container = container.parentElement;
    }

    return video.parentElement || video;
  }

  // Create the floating IDM-style panel
  function createPanel(video, container) {
    if (container.querySelector(".hdm-video-panel")) return;

    // Ensure container has relative/absolute positioning
    const compStyle = window.getComputedStyle(container);
    if (compStyle.position === "static") {
      container.style.position = "relative";
    }

    const panel = document.createElement("div");
    panel.className = "hdm-video-panel";

    // Main pill
    const pill = document.createElement("div");
    pill.className = "hdm-panel-pill";
    pill.title = "Tải video này về máy với HDM";

    const iconSpan = document.createElement("span");
    iconSpan.className = "hdm-icon";
    iconSpan.innerHTML = SVG_DOWNLOAD_ICON;

    const labelSpan = document.createElement("span");
    labelSpan.className = "hdm-label";
    labelSpan.textContent = "Tải video này";

    const badgeSpan = document.createElement("span");
    badgeSpan.className = "hdm-badge";
    badgeSpan.textContent = isYouTube() ? "YT" : "MP4";

    const arrowSpan = document.createElement("span");
    arrowSpan.className = "hdm-arrow";
    arrowSpan.innerHTML = SVG_ARROW_ICON;

    const closeBtn = document.createElement("span");
    closeBtn.className = "hdm-close-btn";
    closeBtn.textContent = "×";
    closeBtn.title = "Ẩn nút tải cho video này";

    pill.appendChild(iconSpan);
    pill.appendChild(labelSpan);
    pill.appendChild(badgeSpan);
    pill.appendChild(arrowSpan);
    pill.appendChild(closeBtn);
    panel.appendChild(pill);

    // Dropdown menu
    const dropdown = document.createElement("div");
    dropdown.className = "hdm-dropdown";

    const itemBest = document.createElement("div");
    itemBest.className = "hdm-dropdown-item";
    itemBest.innerHTML = `
      <div class="hdm-item-title">🎬 Tải video chất lượng cao (MP4)</div>
      <div class="hdm-item-badge">HD</div>
    `;

    const itemAudio = document.createElement("div");
    itemAudio.className = "hdm-dropdown-item";
    itemAudio.innerHTML = `
      <div class="hdm-item-title">🎵 Tải chỉ âm thanh (MP3 / Audio)</div>
      <div class="hdm-item-badge">AUDIO</div>
    `;

    dropdown.appendChild(itemBest);
    dropdown.appendChild(itemAudio);
    panel.appendChild(dropdown);

    // Toggle dropdown on arrow click
    arrowSpan.addEventListener("click", (e) => {
      e.stopPropagation();
      panel.classList.toggle("open");
    });

    // Close button
    closeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      panel.style.display = "none";
    });

    // Close dropdown on outside click
    document.addEventListener("click", (e) => {
      if (!panel.contains(e.target)) {
        panel.classList.remove("open");
      }
    });

    // Trigger download
    function triggerDownload(formatType) {
      panel.classList.remove("open");
      labelSpan.textContent = "✓ Đang mở HDM...";
      pill.classList.add("success");

      setTimeout(() => {
        labelSpan.textContent = "Tải video này";
        pill.classList.remove("success");
      }, 2500);

      const pageUrl = window.location.href;
      let targetUrl = pageUrl;

      if (!isYouTube()) {
        const rawSrc = video.currentSrc || video.src;
        if (rawSrc && !rawSrc.startsWith("blob:")) {
          targetUrl = rawSrc;
        }
      }

      chrome.runtime.sendMessage({
        action: "download_media",
        data: {
          url: targetUrl,
          pageUrl: pageUrl,
          title: getVideoTitle(),
          format: formatType || "mp4",
          isStreaming: isYouTube(),
        },
      });
    }

    // Click on main pill triggers best video download
    pill.addEventListener("click", (e) => {
      if (e.target === closeBtn || e.target === arrowSpan || arrowSpan.contains(e.target)) return;
      triggerDownload("mp4");
    });

    itemBest.addEventListener("click", (e) => {
      e.stopPropagation();
      triggerDownload("mp4");
    });

    itemAudio.addEventListener("click", (e) => {
      e.stopPropagation();
      triggerDownload("mp3");
    });

    // Auto-idle fading behavior
    let idleTimeout = null;
    function resetIdle() {
      panel.classList.remove("idle");
      clearTimeout(idleTimeout);
      if (!video.paused) {
        idleTimeout = setTimeout(() => {
          if (!panel.matches(":hover") && !panel.classList.contains("open")) {
            panel.classList.add("idle");
          }
        }, 3500);
      }
    }

    container.addEventListener("mousemove", resetIdle);
    container.addEventListener("mouseenter", resetIdle);
    video.addEventListener("play", resetIdle);
    video.addEventListener("pause", () => {
      panel.classList.remove("idle");
      clearTimeout(idleTimeout);
    });

    container.appendChild(panel);
  }

  // Scan and hook all videos on the page
  function scanVideos() {
    chrome.storage.local.get({ enableVideoPanel: true }, (settings) => {
      if (!settings.enableVideoPanel) return;

      const videos = document.querySelectorAll("video");
      videos.forEach((vid) => {
        // Skip tiny audio-only or hidden elements
        if (vid.offsetWidth < 120 && vid.offsetHeight < 80 && !isYouTube()) return;
        const container = findAnchorContainer(vid);
        if (container) {
          createPanel(vid, container);
        }
      });
    });
  }

  // Observe dynamically loaded video players
  const observer = new MutationObserver(() => {
    scanVideos();
  });

  observer.observe(document.body || document.documentElement, {
    childList: true,
    subtree: true,
  });

  // Listen to YouTube SPA navigation events
  window.addEventListener("yt-navigate-finish", () => {
    setTimeout(scanVideos, 600);
  });
  window.addEventListener("popstate", () => {
    setTimeout(scanVideos, 600);
  });

  // Initial scan
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scanVideos);
  } else {
    scanVideos();
  }
})();
