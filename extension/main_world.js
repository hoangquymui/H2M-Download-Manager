/**
 * HDM Browser Extension - MAIN world helper.
 * Runs in the page's own JS context (not the isolated content-script world) so it
 * can read player globals (jwplayer) and intercept URL.createObjectURL blobs.
 * Forwards discovered HLS playlists / stream URLs to content.js via postMessage.
 */

(function () {
  "use strict";

  if (window.__HDM_MAIN_WORLD_LOADED__) return;
  window.__HDM_MAIN_WORLD_LOADED__ = true;

  const MAX_MANIFEST_BYTES = 4 * 1024 * 1024;
  const MAX_BLOB_SIZE = 4 * 1024 * 1024;
  const MAX_BLOBS = 16;
  const MAX_QUALITIES = 8;
  const MAX_QUALITIES_BYTES = 5 * 1024 * 1024;

  let lastManifest = "";
  let lastManifestHasSegments = false;
  let lastStreamUrl = "";
  let lastUrlPublished = "";
  let lastQualities = [];
  let lastQualitiesKey = "";

  // Map blob: URL -> playlist text. Players that build HLS in JS (hoathinh3d /
  // ibytedance, etc.) hand the player one blob per quality level, and a master
  // playlist whose variants point at those blobs; keeping the texts lets us
  // resolve every quality instead of only the one that happens to load.
  const blobTexts = new Map();

  function publish(obj) {
    try {
      window.postMessage(Object.assign({ __hdm_main: true }, obj), "*");
    } catch (e) {}
  }

  function rememberBlobText(url, text) {
    if (!url || !text) return;
    blobTexts.set(url, text);
    while (blobTexts.size > MAX_BLOBS) {
      const oldest = blobTexts.keys().next().value;
      blobTexts.delete(oldest);
    }
  }

  function parseMaster(text) {
    const lines = text.split(/\r?\n/);
    const variants = [];
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (line.indexOf("#EXT-X-STREAM-INF") !== 0) continue;
      const res = /RESOLUTION=(\d+)x(\d+)/i.exec(line);
      const bw = /BANDWIDTH=(\d+)/i.exec(line);
      let uri = "";
      for (let j = i + 1; j < lines.length; j++) {
        const next = lines[j].trim();
        if (!next || next.charAt(0) === "#") continue;
        uri = next;
        break;
      }
      if (uri) {
        variants.push({ height: res ? res[2] : "", bandwidth: bw ? bw[1] : "", uri: uri });
      }
    }
    return variants;
  }

  function parseHeight(label) {
    const m = /(\d{3,4})\s*p?/i.exec(label || "");
    return m ? m[1] : "";
  }

  function buildQualities() {
    const out = [];
    const seen = new Set();

    // 1. Best source: a captured master playlist whose variant URIs are blobs
    //    created in this page, so their texts are available.
    for (const master of blobTexts.values()) {
      if (master.indexOf("#EXT-X-STREAM-INF") === -1) continue;
      for (const v of parseMaster(master)) {
        const manifest = v.uri.indexOf("blob:") === 0 ? blobTexts.get(v.uri) || "" : "";
        if (!manifest || manifest.indexOf("#EXTM3U") === -1) continue;
        const height = v.height || "";
        const label = height ? `${height}p` : "";
        const key = `${label}:${manifest.length}`;
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({ label: label, height: height, manifest: manifest });
      }
      if (out.length) break;
    }

    // 2. Fallback: jwplayer exposes the same list as playlist sources.
    if (!out.length) {
      try {
        const player = typeof window.jwplayer === "function" ? window.jwplayer() : null;
        const item = player && player.getPlaylistItem ? player.getPlaylistItem() : null;
        const sources = (item && item.sources) || [];
        for (const src of sources) {
          if (!src || typeof src.file !== "string" || src.file.indexOf("blob:") !== 0) continue;
          const manifest = blobTexts.get(src.file) || "";
          if (!manifest || manifest.indexOf("#EXTM3U") === -1) continue;
          const height = String(src.height || parseHeight(src.label) || "");
          const label = String(src.label || (height ? `${height}p` : ""));
          const key = `${label}:${manifest.length}`;
          if (seen.has(key)) continue;
          seen.add(key);
          out.push({ label: label, height: height, manifest: manifest });
        }
      } catch (e) {}
    }

    out.sort((a, b) => (parseInt(b.height, 10) || 0) - (parseInt(a.height, 10) || 0));
    const limited = [];
    let total = 0;
    for (const q of out) {
      if (limited.length >= MAX_QUALITIES) break;
      if (total + q.manifest.length > MAX_QUALITIES_BYTES) break;
      total += q.manifest.length;
      limited.push(q);
    }
    return limited;
  }

  function hasBlobUris(text) {
    if (!text) return false;
    return text.split(/\r?\n/).some((line) => {
      const value = line.trim();
      return value && value.charAt(0) !== "#" && value.indexOf("blob:") === 0;
    });
  }

  function refreshQualities() {
    const qualities = buildQualities();
    // A master playlist whose variants are blob: URLs cannot be fetched on the
    // desktop; use the resolved highest-quality playlist as the default instead.
    if (qualities.length && hasBlobUris(lastManifest)) {
      lastManifest = qualities[0].manifest;
      lastManifestHasSegments = true;
    }
    const key = qualities.map((q) => `${q.label}:${q.manifest.length}`).join("|");
    if (key === lastQualitiesKey) return;
    lastQualitiesKey = key;
    lastQualities = qualities;
  }

  function rememberManifest(text) {
    if (!text || typeof text !== "string") return;
    if (text.length > MAX_MANIFEST_BYTES) return;
    if (text.indexOf("#EXTM3U") === -1) return;

    const hasSegments = text.indexOf("#EXTINF") !== -1;
    // A media playlist is always more useful than a master playlist; otherwise
    // keep the first master we saw until a real media playlist arrives.
    if (!lastManifest || hasSegments || !lastManifestHasSegments) {
      lastManifest = text;
      lastManifestHasSegments = hasSegments;
    }
    refreshQualities();
  }

  function rememberUrl(url) {
    if (!url || typeof url !== "string") return;
    if (!/^https?:/i.test(url)) return;
    if (!/\.m3u8|\.mpd/i.test(url)) return;
    lastStreamUrl = url;
  }

  // Video sites (jwplayer based: ibytedance/hoathinh3d, etc.) often generate the
  // HLS manifest in JS and hand a blob: URL to the player, so no network request
  // for .m3u8 exists to sniff. Capture the blob payload at creation time.
  try {
    const originalCreateObjectURL = URL.createObjectURL;
    URL.createObjectURL = function (obj) {
      const url = originalCreateObjectURL.call(URL, obj);
      try {
        if (obj instanceof Blob && obj.size > 0 && obj.size <= MAX_BLOB_SIZE) {
          const type = (obj.type || "").toLowerCase();
          const maybePlaylist =
            type.indexOf("mpegurl") !== -1 ||
            type.indexOf("m3u") !== -1 ||
            type.indexOf("dash") !== -1 ||
            type === "";
          if (maybePlaylist) {
            obj
              .text()
              .then((text) => {
                if (text && text.indexOf("#EXTM3U") !== -1) {
                  rememberBlobText(url, text);
                  rememberManifest(text);
                }
              })
              .catch(() => {});
          }
        }
      } catch (e) {}
      return url;
    };
  } catch (e) {}

  function probeJwPlayer() {
    try {
      if (typeof window.jwplayer !== "function") return;
      const player = window.jwplayer();
      if (!player) return;
      const playlist = player.getPlaylist() || [];
      for (const item of playlist) {
        if (!item) continue;
        if (typeof item.file === "string" && item.file.indexOf("blob:") !== 0) {
          rememberUrl(item.file);
        }
        if (Array.isArray(item.sources)) {
          for (const source of item.sources) {
            if (source && typeof source.file === "string" && source.file.indexOf("blob:") !== 0) {
              rememberUrl(source.file);
            }
          }
        }
      }
    } catch (e) {}
  }

  function republish() {
    if (lastManifest) {
      publish({
        type: "HDM_MAIN_MANIFEST",
        manifest: lastManifest,
        qualities: lastQualities,
        pageUrl: location.href,
      });
      if (lastManifestHasSegments && !lastStreamUrl) return;
    }
    if (lastStreamUrl && lastStreamUrl !== lastUrlPublished) {
      lastUrlPublished = lastStreamUrl;
      publish({ type: "HDM_MAIN_STREAM_URL", url: lastStreamUrl, pageUrl: location.href });
    }
  }

  setInterval(() => {
    probeJwPlayer();
    refreshQualities();
    republish();
  }, 1000);

  probeJwPlayer();
  republish();
})();
