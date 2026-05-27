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

const videoPlayer = document.getElementById("video-player");
const playBtn     = document.getElementById("play-btn");
const stopBtn     = document.getElementById("stop-btn");

const statusBar     = document.getElementById("status-bar");
const cachedSelect  = document.getElementById("cached-select");
const cachedLoadBtn = document.getElementById("cached-load-btn");

let currentVideo  = null;
let pollTimer     = null;
let isDownloading = false;

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
async function loadCachedVideos() {
    try {
        const resp = await fetch("/videos");
        if (!resp.ok) return;
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
    } catch (e) { /* non-critique */ }
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
    cachedLoadBtn.disabled = !cachedSelect.value;
});
cachedLoadBtn.addEventListener("click", loadCachedVideo);

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

// ── Play / Stop ──
async function play() {
    playBtn.disabled = true;
    setStatus("Démarrage du rejeu…");
    try {
        videoPlayer.currentTime = 0;
        await videoPlayer.play();
        const resp = await fetch("/play", { method: "POST" });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            videoPlayer.pause();
            throw new Error(err.detail || "Impossible de démarrer le rejeu");
        }
        stopBtn.disabled = false;
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
        playBtn.disabled = false;
    } catch (e) {
        setStatus(e.message, "error");
    }
}

videoPlayer.addEventListener("ended", () => {
    setStatus("Rejeu terminé", "ok");
    stopBtn.disabled = true;
    playBtn.disabled = false;
});

// ── Listeners ──
uploadBtn.addEventListener("click", uploadVideo);
ytBtn.addEventListener("click", downloadYoutube);
processBtn.addEventListener("click", processVideo);
playBtn.addEventListener("click", play);
stopBtn.addEventListener("click", stop);

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
        if (s.status_message) setStatus(s.status_message);
    } catch (e) {
        setStatus("Backend non joignable", "error");
    }
})();
