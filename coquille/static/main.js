// Coquille — UI logic

const fileInput    = document.getElementById("file-input");
const uploadBtn    = document.getElementById("upload-btn");
const fileLabel    = document.querySelector(".file-label");
const ytInput      = document.getElementById("yt-input");
const ytBtn        = document.getElementById("yt-btn");
const uploadInfo   = document.getElementById("upload-info");

const processBtn      = document.getElementById("process-btn");
const processInfo     = document.getElementById("process-info");
const processProgress = document.getElementById("process-progress");

const videoPlayer  = document.getElementById("video-player");
const playBtn      = document.getElementById("play-btn");
const pauseBtn     = document.getElementById("pause-btn");
const stopBtn      = document.getElementById("stop-btn");
const seekControls = document.getElementById("seek-controls");
const seekBackBtn  = document.getElementById("seek-back-btn");
const seekFwdBtn   = document.getElementById("seek-fwd-btn");

const statusBar       = document.getElementById("status-bar");
const cachedSelect    = document.getElementById("cached-select");
const cachedLoadBtn   = document.getElementById("cached-load-btn");
const cachedDeleteBtn = document.getElementById("cached-delete-btn");

let currentVideo  = null;
let pollTimer     = null;
let isDownloading = false;
let isPaused      = false;

// ── Afficher le nom du fichier sélectionné ──
fileInput.addEventListener("change", () => {
    const file = fileInput.files && fileInput.files[0];
    if (file) {
        fileLabel.textContent = `✔ ${file.name}`;
        fileLabel.style.borderColor = "#3b82f6";
        fileLabel.style.color = "#dde1f0";
    } else {
        fileLabel.textContent = "📁 Fichier";
        fileLabel.style.borderColor = "";
        fileLabel.style.color = "";
    }
});

// ── Vidéos en cache ──
async function loadCachedVideos(retries = 0) {
    try {
        const resp = await fetch("/videos");
        if (!resp.ok) {
            if (retries < 4) setTimeout(() => loadCachedVideos(retries + 1), 1500);
            return;
        }
        const data = await resp.json();
        const videos = data.videos || [];
        const prev = cachedSelect.value;
        cachedSelect.innerHTML = '<option value="">— Vidéos déjà traitées —</option>';
        videos.forEach(v => {
            const opt = document.createElement("option");
            opt.value = v;
            opt.textContent = v;
            cachedSelect.appendChild(opt);
        });
        if (prev && videos.includes(prev)) cachedSelect.value = prev;
        const hasSelection = !!cachedSelect.value;
        cachedLoadBtn.disabled = !hasSelection;
        cachedDeleteBtn.disabled = !hasSelection;
    } catch (e) {
        if (retries < 4) setTimeout(() => loadCachedVideos(retries + 1), 1500);
    }
}

async function loadCachedVideo() {
    const filename = cachedSelect.value;
    if (!filename) return;
    cachedLoadBtn.disabled = true;
    setStatus(`Chargement de "${filename}"...`);
    try {
        const resp = await fetch("/select_video", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filename }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || "Erreur lors du chargement");
        }
        const data = await resp.json();
        currentVideo = data.filename;
        uploadInfo.textContent = `Vidéo chargée : ${currentVideo}`;
        videoPlayer.src = `/video/${encodeURIComponent(currentVideo)}`;
        if (data.cached) {
            processBtn.disabled = false;
            playBtn.disabled = false;
            stopBtn.disabled = true;
            processProgress.hidden = true;
            processInfo.textContent = "Mouvement chargé depuis le cache";
            setStatus(`Mouvement prêt pour "${currentVideo}"`, "ok");
        } else {
            processBtn.disabled = false;
            playBtn.disabled = true;
            stopBtn.disabled = true;
            processInfo.textContent = "Prêt à être traité";
            setStatus(`Vidéo "${currentVideo}" chargée — lancez le pipeline`, "ok");
        }
    } catch (e) {
        uploadInfo.textContent = `Erreur : ${e.message}`;
        setStatus(e.message, "error");
    } finally {
        cachedLoadBtn.disabled = !cachedSelect.value;
    }
}

cachedSelect.addEventListener("change", () => {
    const hasSelection = !!cachedSelect.value;
    cachedLoadBtn.disabled = !hasSelection;
    cachedDeleteBtn.disabled = !hasSelection;
});
cachedLoadBtn.addEventListener("click", loadCachedVideo);

async function deleteCachedVideo() {
    const filename = cachedSelect.value;
    if (!filename) return;
    if (!confirm(`Supprimer "${filename}" et tous ses fichiers associés ?`)) return;

    cachedDeleteBtn.disabled = true;
    cachedLoadBtn.disabled = true;
    setStatus(`Suppression de "${filename}"…`);
    try {
        const resp = await fetch(`/videos/${encodeURIComponent(filename)}`, { method: "DELETE" });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || "Erreur lors de la suppression");
        }
        if (currentVideo === filename) {
            currentVideo = null;
            uploadInfo.textContent = "Aucune vidéo chargée";
            videoPlayer.src = "";
            processBtn.disabled = true;
            playBtn.disabled = true;
            stopBtn.disabled = true;
            processInfo.textContent = "En attente d'une vidéo";
        }
        setStatus(`"${filename}" supprimé`, "ok");
        await loadCachedVideos();
    } catch (e) {
        setStatus(e.message, "error");
        cachedDeleteBtn.disabled = !cachedSelect.value;
        cachedLoadBtn.disabled = !cachedSelect.value;
    }
}
cachedDeleteBtn.addEventListener("click", deleteCachedVideo);

// ── Status bar ──
function setStatus(msg, kind) {
    statusBar.textContent = `Statut : ${msg}`;
    statusBar.className = kind ? `status-${kind}` : "";
}

// ── Upload fichier ──
async function uploadVideo() {
    const file = fileInput.files && fileInput.files[0];
    if (!file) {
        uploadInfo.textContent = "Aucun fichier sélectionné.";
        return;
    }
    uploadBtn.disabled = true;
    uploadInfo.textContent = `Upload de "${file.name}"…`;
    setStatus("Upload en cours…");

    try {
        const formData = new FormData();
        formData.append("file", file);
        const resp = await fetch("/upload_video", { method: "POST", body: formData });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || "Échec de l'upload");
        }
        const data = await resp.json();
        currentVideo = data.filename;
        uploadInfo.textContent = `Vidéo chargée : ${currentVideo}`;
        videoPlayer.src = `/video/${encodeURIComponent(currentVideo)}`;
        processBtn.disabled = false;
        processInfo.textContent = "Prêt à être traité";
        playBtn.disabled = true;
        stopBtn.disabled = true;
        setStatus(`Vidéo "${currentVideo}" chargée`, "ok");
        processVideo();
    } catch (e) {
        uploadInfo.textContent = `Erreur : ${e.message}`;
        setStatus(e.message, "error");
    } finally {
        uploadBtn.disabled = false;
    }
}

// ── Pipeline ──
async function processVideo() {
    if (!currentVideo) return;
    processBtn.disabled = true;
    playBtn.disabled = true;
    stopBtn.disabled = true;
    processProgress.hidden = false;
    processProgress.value = 0;
    processInfo.textContent = "Démarrage…";
    setStatus("Traitement de la vidéo…");

    try {
        const resp = await fetch("/process_video", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filename: currentVideo }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || "Échec du démarrage du pipeline");
        }
        startPolling();
    } catch (e) {
        processInfo.textContent = `Erreur : ${e.message}`;
        setStatus(e.message, "error");
        processBtn.disabled = false;
        processProgress.hidden = true;
    }
}

// ── Polling ──
function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollStatus, 500);
}

function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

// ── YouTube ──
async function downloadYoutube() {
    const url = ytInput.value.trim();
    if (!url) return;
    ytBtn.disabled = true;
    uploadBtn.disabled = true;
    isDownloading = true;
    uploadInfo.textContent = "Téléchargement en cours…";
    setStatus("Téléchargement YouTube…");

    try {
        const resp = await fetch("/download_youtube", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || "Échec du téléchargement");
        }
        startPolling();
    } catch (e) {
        isDownloading = false;
        uploadInfo.textContent = `Erreur : ${e.message}`;
        setStatus(e.message, "error");
        ytBtn.disabled = false;
        uploadBtn.disabled = false;
    }
}

// ── Poll status ──
async function pollStatus() {
    try {
        const resp = await fetch("/status");
        if (!resp.ok) return;
        const s = await resp.json();

        if (s.processing_status === "downloading") {
            uploadInfo.textContent = s.status_message || "Téléchargement…";
            setStatus(s.status_message || "Téléchargement YouTube…");

        } else if (isDownloading && s.processing_status === "idle") {
            isDownloading = false;
            stopPolling();
            ytBtn.disabled = false;
            uploadBtn.disabled = false;
            currentVideo = s.current_video;
            uploadInfo.textContent = `Vidéo téléchargée : ${currentVideo}`;
            videoPlayer.src = `/video/${encodeURIComponent(currentVideo)}`;
            processBtn.disabled = false;
            playBtn.disabled = true;
            stopBtn.disabled = true;
            setStatus(`Vidéo "${currentVideo}" prête`, "ok");
            processVideo();

        } else if (isDownloading && s.processing_status === "error") {
            isDownloading = false;
            stopPolling();
            ytBtn.disabled = false;
            uploadBtn.disabled = false;
            uploadInfo.textContent = s.status_message || "Erreur téléchargement";
            setStatus(s.status_message || "Erreur téléchargement", "error");

        } else if (s.processing_status === "extracting") {
            processInfo.textContent = s.status_message || "Extraction des signaux…";
            processProgress.value = 33;

        } else if (s.processing_status === "mapping") {
            processInfo.textContent = s.status_message || "Génération du mouvement…";
            processProgress.value = 66;

        } else if (s.processing_status === "ready") {
            processInfo.textContent = s.status_message || "Mouvement prêt";
            processProgress.value = 100;
            stopPolling();
            processBtn.disabled = false;
            playBtn.disabled = false;
            stopBtn.disabled = true;
            setStatus("Mouvement prêt — vous pouvez lancer le rejeu", "ok");
            setTimeout(() => { processProgress.hidden = true; }, 1000);
            loadCachedVideos();

        } else if (s.processing_status === "error") {
            processInfo.textContent = s.status_message || "Erreur lors du traitement";
            stopPolling();
            processBtn.disabled = false;
            processProgress.hidden = true;
            setStatus(s.status_message || "Erreur de traitement", "error");
        }
    } catch (e) {
        // backend momentanément indisponible
    }
}

// ── UI state helpers ──
function setPlayingUI() {
    playBtn.hidden = true;
    pauseBtn.hidden = false; pauseBtn.disabled = false;
    stopBtn.disabled = false;
    seekControls.hidden = true;
}
function setPausedUI() {
    playBtn.hidden = true;
    pauseBtn.hidden = false; pauseBtn.disabled = false;
    stopBtn.disabled = false;
    seekControls.hidden = false;
}
function setIdleUI() {
    playBtn.hidden = false; playBtn.disabled = false;
    pauseBtn.hidden = true;
    stopBtn.disabled = true;
    seekControls.hidden = true;
}

// ── Play / Stop / Pause / Seek ──
async function play() {
    playBtn.disabled = true;
    setStatus("Démarrage du rejeu…");
    try {
        videoPlayer.currentTime = 0;
        const t0 = performance.now();
        const resp = await fetch("/play", { method: "POST" });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || "Impossible de démarrer le rejeu");
        }
        // Compense le délai réseau : le robot a déjà démarré depuis RTT/2 ms
        const elapsed = (performance.now() - t0) / 1000;
        videoPlayer.currentTime = elapsed / 2;
        await videoPlayer.play();
        isPaused = false;
        pauseBtn.textContent = "⏸ Pause";
        setPlayingUI();
        setStatus("Rejeu en cours (robot + vidéo)", "playing");
    } catch (e) {
        setStatus(e.message, "error");
        playBtn.disabled = false;
    }
}

async function stop() {
    stopBtn.disabled = true;
    try {
        await fetch("/stop", { method: "POST" });
        videoPlayer.pause();
        setStatus("Rejeu arrêté", "ok");
        isPaused = false;
        setIdleUI();
    } catch (e) {
        setStatus(e.message, "error");
        stopBtn.disabled = false;
    }
}

async function togglePause() {
    pauseBtn.disabled = true;
    if (!isPaused) {
        const resp = await fetch("/pause", { method: "POST" });
        if (!resp.ok) { pauseBtn.disabled = false; return; }
        videoPlayer.pause();
        isPaused = true;
        pauseBtn.textContent = "▶ Reprendre";
        setPausedUI();
        setStatus("En pause", "ok");
    } else {
        const resp = await fetch("/resume", { method: "POST" });
        if (!resp.ok) { pauseBtn.disabled = false; return; }
        const data = await resp.json();
        videoPlayer.currentTime = data.elapsed;
        await videoPlayer.play();
        isPaused = false;
        pauseBtn.textContent = "⏸ Pause";
        setPlayingUI();
        setStatus("Rejeu en cours (robot + vidéo)", "playing");
    }
}

async function seek(delta) {
    seekBackBtn.disabled = seekFwdBtn.disabled = true;
    const resp = await fetch("/seek", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ delta }),
    });
    if (resp.ok) {
        const data = await resp.json();
        videoPlayer.currentTime = Math.max(0, Math.min(data.elapsed, videoPlayer.duration || Infinity));
        setStatus(`Position : ${data.elapsed.toFixed(1)}s`, "ok");
    }
    seekBackBtn.disabled = seekFwdBtn.disabled = false;
}

videoPlayer.addEventListener("ended", () => {
    setStatus("Rejeu terminé", "ok");
    isPaused = false;
    setIdleUI();
});

// ── Listeners ──
uploadBtn.addEventListener("click", uploadVideo);
ytBtn.addEventListener("click", downloadYoutube);
processBtn.addEventListener("click", processVideo);
playBtn.addEventListener("click", play);
stopBtn.addEventListener("click", stop);
pauseBtn.addEventListener("click", togglePause);
seekBackBtn.addEventListener("click", () => seek(-10));
seekFwdBtn.addEventListener("click",  () => seek(+10));

// ── Init : synchronise l'UI avec le backend ──
(async function init() {
    loadCachedVideos();
    try {
        const resp = await fetch("/status");
        if (!resp.ok) return;
        const s = await resp.json();
        if (s.current_video) {
            currentVideo = s.current_video;
            uploadInfo.textContent = `Vidéo chargée : ${currentVideo}`;
            videoPlayer.src = `/video/${encodeURIComponent(currentVideo)}`;
            processBtn.disabled = false;
        }
        if (s.frame_count > 0) {
            playBtn.disabled = false;
            processInfo.textContent = `Mouvement prêt (${s.frame_count} frames, ${s.duration.toFixed(1)}s)`;
        }
        if (s.is_replaying && s.is_paused) {
            isPaused = true;
            pauseBtn.textContent = "▶ Reprendre";
            videoPlayer.currentTime = s.paused_elapsed || 0;
            setPausedUI();
        } else if (s.is_replaying) {
            isPaused = false;
            pauseBtn.textContent = "⏸ Pause";
            setPlayingUI();
        }
        if (s.status_message) setStatus(s.status_message);
    } catch (e) {
        setStatus("Backend non joignable", "error");
    }
})();
