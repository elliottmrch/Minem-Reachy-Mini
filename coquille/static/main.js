// Coquille — UI logic
// Pipeline vidéo -> robot : upload, traitement, rejeu synchrone.

const fileInput = document.getElementById("file-input");
const uploadBtn = document.getElementById("upload-btn");
const ytInput = document.getElementById("yt-input");
const ytBtn = document.getElementById("yt-btn");
const uploadInfo = document.getElementById("upload-info");

const processBtn = document.getElementById("process-btn");
const processInfo = document.getElementById("process-info");
const processProgress = document.getElementById("process-progress");

const videoPlayer = document.getElementById("video-player");
const playBtn = document.getElementById("play-btn");
const stopBtn = document.getElementById("stop-btn");

const statusBar = document.getElementById("status-bar");

let currentVideo = null;       // nom du fichier .mp4 chargé côté backend
let pollTimer = null;          // setInterval pour /status pendant le traitement
let isDownloading = false;     // true pendant un téléchargement YouTube

function setStatus(msg, kind) {
    statusBar.textContent = `Statut : ${msg}`;
    statusBar.className = kind ? `status-${kind}` : "";
}

async function uploadVideo() {
    const file = fileInput.files && fileInput.files[0];
    if (!file) {
        uploadInfo.textContent = "Aucun fichier sélectionné.";
        return;
    }
    uploadBtn.disabled = true;
    uploadInfo.textContent = `Upload de "${file.name}"...`;
    setStatus("Upload en cours...");

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
    } catch (e) {
        uploadInfo.textContent = `Erreur : ${e.message}`;
        setStatus(e.message, "error");
    } finally {
        uploadBtn.disabled = false;
    }
}

async function processVideo() {
    if (!currentVideo) return;
    processBtn.disabled = true;
    playBtn.disabled = true;
    stopBtn.disabled = true;
    processProgress.hidden = false;
    processProgress.value = 0;
    processInfo.textContent = "Démarrage...";
    setStatus("Traitement de la vidéo...");

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

function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollStatus, 500);
}

function stopPolling() {
    if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
    }
}

async function downloadYoutube() {
    const url = ytInput.value.trim();
    if (!url) return;
    ytBtn.disabled = true;
    uploadBtn.disabled = true;
    isDownloading = true;
    uploadInfo.textContent = "Téléchargement en cours...";
    setStatus("Téléchargement YouTube...");

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

async function pollStatus() {
    try {
        const resp = await fetch("/status");
        if (!resp.ok) return;
        const s = await resp.json();

        if (s.processing_status === "downloading") {
            uploadInfo.textContent = s.status_message || "Téléchargement...";
            setStatus(s.status_message || "Téléchargement YouTube...");
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
        } else if (isDownloading && s.processing_status === "error") {
            isDownloading = false;
            stopPolling();
            ytBtn.disabled = false;
            uploadBtn.disabled = false;
            uploadInfo.textContent = s.status_message || "Erreur téléchargement";
            setStatus(s.status_message || "Erreur téléchargement", "error");
        } else if (s.processing_status === "extracting") {
            processInfo.textContent = s.status_message || "Extraction des signaux...";
            processProgress.value = 33;
        } else if (s.processing_status === "mapping") {
            processInfo.textContent = s.status_message || "Génération du mouvement...";
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
        } else if (s.processing_status === "error") {
            processInfo.textContent = s.status_message || "Erreur lors du traitement";
            stopPolling();
            processBtn.disabled = false;
            processProgress.hidden = true;
            setStatus(s.status_message || "Erreur de traitement", "error");
        }
    } catch (e) {
        // backend momentanément indisponible — on continue le polling
    }
}

async function play() {
    playBtn.disabled = true;
    setStatus("Démarrage du rejeu...");

    try {
        // Vidéo d'abord : attend que le navigateur soit vraiment en train de jouer
        videoPlayer.currentTime = 0;
        await videoPlayer.play();

        // Robot ensuite : t0 est noté ici, quand la vidéo joue déjà
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

uploadBtn.addEventListener("click", uploadVideo);
ytBtn.addEventListener("click", downloadYoutube);
processBtn.addEventListener("click", processVideo);
playBtn.addEventListener("click", play);
stopBtn.addEventListener("click", stop);

// État initial : synchronise l'UI avec ce que le backend pourrait déjà connaître
(async function init() {
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
        if (s.status_message) {
            setStatus(s.status_message);
        }
    } catch (e) {
        setStatus("Backend non joignable", "error");
    }
})();
