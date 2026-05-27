// ══════════════════════════════════════════════════════════════════════════════
// main.js — Logique UI de l'application Coquille
//
// Ce script gère TOUTES les interactions entre l'interface HTML et l'API FastAPI.
// Il n'a aucune dépendance externe (vanilla JS, pas de framework).
//
// Organisation :
//   1. Références DOM  — tous les éléments HTML manipulés
//   2. État local      — variables de l'UI (vidéo courante, polling, pause…)
//   3. Gestion vidéos  — cache, upload, YouTube, sélection, suppression
//   4. Status bar      — setStatus() et son usage
//   5. Upload fichier  — uploadVideo()
//   6. Pipeline        — processVideo(), polling, pollStatus()
//   7. Playback        — play(), stop(), togglePause(), seek()
//   8. Mode Live       — switchMode(), startLive(), stopLive(), pollLiveCalibration()
//   9. Init            — synchronisation UI avec l'état backend au chargement
// ══════════════════════════════════════════════════════════════════════════════


// ── 1. Références DOM ─────────────────────────────────────────────────────────
// Toutes les références aux éléments HTML sont regroupées ici pour faciliter
// la navigation dans le code.

// Bloc import vidéo
const fileInput    = document.getElementById("file-input");    // input[type=file] (caché)
const uploadBtn    = document.getElementById("upload-btn");    // bouton "Upload"
const fileLabel    = document.querySelector(".file-label");    // label visuel du file input
const ytInput      = document.getElementById("yt-input");      // champ URL YouTube
const ytBtn        = document.getElementById("yt-btn");        // bouton "⬇ YouTube"
const uploadInfo   = document.getElementById("upload-info");   // texte info sous le bloc import

// Bloc pipeline traitement
const processBtn      = document.getElementById("process-btn");      // bouton "⚙ Lancer le pipeline"
const processInfo     = document.getElementById("process-info");     // texte info pipeline
const processProgress = document.getElementById("process-progress"); // barre de progression

// Lecteur vidéo et contrôles de rejeu
const videoPlayer  = document.getElementById("video-player");    // <video>
const playBtn      = document.getElementById("play-btn");         // bouton ▶ Play
const pauseBtn     = document.getElementById("pause-btn");        // bouton ⏸ Pause / ▶ Reprendre
const stopBtn      = document.getElementById("stop-btn");         // bouton ⏹ Stop
const seekControls = document.getElementById("seek-controls");    // conteneur boutons seek
const seekBackBtn  = document.getElementById("seek-back-btn");    // bouton ⏮ -10s
const seekFwdBtn   = document.getElementById("seek-fwd-btn");     // bouton +10s ⏭

// Barre de statut et sélection des vidéos cachées
const statusBar       = document.getElementById("status-bar");        // barre de statut en haut
const cachedSelect    = document.getElementById("cached-select");      // <select> vidéos traitées
const cachedLoadBtn   = document.getElementById("cached-load-btn");    // bouton "Charger"
const cachedDeleteBtn = document.getElementById("cached-delete-btn");  // bouton 🗑 Supprimer


// ── 2. État local de l'UI ─────────────────────────────────────────────────────
// Variables qui trackent l'état courant côté navigateur.
// Elles sont synchronisées avec le backend via /status au chargement et pendant le polling.

let currentVideo  = null;   // nom de la vidéo actuellement sélectionnée (ex: "discours.mp4")
let pollTimer     = null;   // référence de l'interval de polling (clearInterval pour arrêter)
let isDownloading = false;  // true pendant un téléchargement YouTube en cours
let isPaused      = false;  // true si le rejeu est en pause (côté UI)


// ── 3a. Affichage du fichier sélectionné ──────────────────────────────────────
// Quand l'utilisateur choisit un fichier, le label affiche son nom.
// Quand aucun fichier n'est sélectionné, on remet l'icône par défaut.
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


// ── 3b. Vidéos déjà traitées (cache) ─────────────────────────────────────────
// Charge et affiche la liste des vidéos ayant un JSON de mouvement associé.
// Appelé au chargement de la page et après chaque traitement réussi.
// Le paramètre `retries` permet de réessayer si le backend n'est pas encore prêt.
async function loadCachedVideos(retries = 0) {
    try {
        const resp = await fetch("/videos");
        if (!resp.ok) {
            // Backend pas encore prêt (ex: démarrage) → on réessaie
            if (retries < 4) setTimeout(() => loadCachedVideos(retries + 1), 1500);
            return;
        }
        const data = await resp.json();
        const videos = data.videos || [];

        // Sauvegarde de la sélection courante pour la restaurer après mise à jour
        const prev = cachedSelect.value;
        cachedSelect.innerHTML = '<option value="">— Vidéos déjà traitées —</option>';
        videos.forEach(v => {
            const opt = document.createElement("option");
            opt.value = v;
            opt.textContent = v;
            cachedSelect.appendChild(opt);
        });
        // Restauration de la sélection précédente si elle existe encore
        if (prev && videos.includes(prev)) cachedSelect.value = prev;

        // Activation des boutons charger/supprimer seulement si une option est sélectionnée
        const hasSelection = !!cachedSelect.value;
        cachedLoadBtn.disabled = !hasSelection;
        cachedDeleteBtn.disabled = !hasSelection;
    } catch (e) {
        if (retries < 4) setTimeout(() => loadCachedVideos(retries + 1), 1500);
    }
}

// Charge en mémoire la vidéo sélectionnée dans le menu déroulant.
// POST /select_video → retourne {filename, cached: bool}
// Si cached=true : le mouvement est chargé, playBtn activé.
// Si cached=false : la vidéo existe mais n'a pas encore été traitée.
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
        // Chargement du player avec la vidéo source (route GET /video/<nom>)
        videoPlayer.src = `/video/${encodeURIComponent(currentVideo)}`;

        if (data.cached) {
            // Mouvement déjà disponible : on peut jouer directement
            processBtn.disabled = false;
            playBtn.disabled = false;
            stopBtn.disabled = true;
            processProgress.hidden = true;
            processInfo.textContent = "Mouvement chargé depuis le cache";
            setStatus(`Mouvement prêt pour "${currentVideo}"`, "ok");
        } else {
            // Vidéo chargée mais pas encore traitée : il faut lancer le pipeline
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

// Activation des boutons charger/supprimer quand une option est sélectionnée dans le menu
cachedSelect.addEventListener("change", () => {
    const hasSelection = !!cachedSelect.value;
    cachedLoadBtn.disabled = !hasSelection;
    cachedDeleteBtn.disabled = !hasSelection;
});
cachedLoadBtn.addEventListener("click", loadCachedVideo);

// Supprime une vidéo et tous ses fichiers associés (DELETE /videos/<nom>).
// Demande confirmation avant de procéder (irréversible).
async function deleteCachedVideo() {
    const filename = cachedSelect.value;
    if (!filename) return;
    // Confirmation utilisateur : la suppression efface vidéo + JSON signaux + JSON mouvement + WAV
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
        // Si la vidéo supprimée était la vidéo active, on remet l'UI en état initial
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
        await loadCachedVideos(); // rafraîchissement de la liste
    } catch (e) {
        setStatus(e.message, "error");
        cachedDeleteBtn.disabled = !cachedSelect.value;
        cachedLoadBtn.disabled = !cachedSelect.value;
    }
}
cachedDeleteBtn.addEventListener("click", deleteCachedVideo);


// ── 4. Barre de statut ────────────────────────────────────────────────────────
// setStatus(msg, kind) met à jour le texte et la classe CSS de la status bar.
// kind : "ok" (vert) | "error" (rouge) | "playing" (orange animé) | undefined (gris)
function setStatus(msg, kind) {
    statusBar.textContent = `Statut : ${msg}`;
    statusBar.className = kind ? `status-${kind}` : "";
}


// ── 5. Upload de fichier ──────────────────────────────────────────────────────
// POST /upload_video avec FormData (multipart/form-data).
// Après un upload réussi, le pipeline est automatiquement lancé (processVideo()).
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
        // multipart/form-data : FastAPI reçoit l'objet UploadFile automatiquement
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
        // Démarrage automatique du pipeline après upload
        processVideo();
    } catch (e) {
        uploadInfo.textContent = `Erreur : ${e.message}`;
        setStatus(e.message, "error");
    } finally {
        uploadBtn.disabled = false;
    }
}


// ── 6a. Pipeline de traitement ────────────────────────────────────────────────
// POST /process_video → le backend lance extraction+mapping+audio en thread daemon.
// La route répond immédiatement {"started": true}, puis on poll /status pour suivre.
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
        // Démarrage du polling toutes les 500ms pour suivre processing_status
        startPolling();
    } catch (e) {
        processInfo.textContent = `Erreur : ${e.message}`;
        setStatus(e.message, "error");
        processBtn.disabled = false;
        processProgress.hidden = true;
    }
}


// ── 6b. Polling de statut ─────────────────────────────────────────────────────
// startPolling() lance un interval toutes les 500ms qui appelle pollStatus().
// stopPolling() l'arrête (après fin de traitement ou erreur).
function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollStatus, 500);
}

function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}


// ── 6c. YouTube ───────────────────────────────────────────────────────────────
// POST /download_youtube → le backend lance yt-dlp dans un thread daemon.
// Même mécanisme que processVideo : retour immédiat + polling.
async function downloadYoutube() {
    const url = ytInput.value.trim();
    if (!url) return;
    ytBtn.disabled = true;
    uploadBtn.disabled = true;
    isDownloading = true; // flag pour que pollStatus() sache qu'on attend un téléchargement
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
        startPolling(); // poll pour suivre la progression du téléchargement
    } catch (e) {
        isDownloading = false;
        uploadInfo.textContent = `Erreur : ${e.message}`;
        setStatus(e.message, "error");
        ytBtn.disabled = false;
        uploadBtn.disabled = false;
    }
}


// ── 6d. Fonction de polling ───────────────────────────────────────────────────
// Appelée toutes les 500ms pendant un traitement ou un téléchargement.
// Lit GET /status et met à jour l'UI en fonction de processing_status.
//
// Machine à états (processing_status) :
//   "downloading"      → mise à jour du message de progression YouTube
//   "idle" (après DL)  → téléchargement terminé → lance processVideo()
//   "extracting"       → barre à 33%, message d'extraction
//   "mapping"          → barre à 66%, message de mapping
//   "ready"            → barre à 100%, arrêt du polling, activation de playBtn
//   "error"            → arrêt du polling, message d'erreur rouge
async function pollStatus() {
    try {
        const resp = await fetch("/status");
        if (!resp.ok) return; // ignore les erreurs transitoires (backend momentanément surchargé)
        const s = await resp.json();

        if (s.processing_status === "downloading") {
            // Téléchargement YouTube en cours : affichage de la progression (ex: "Téléchargement... 45%")
            uploadInfo.textContent = s.status_message || "Téléchargement…";
            setStatus(s.status_message || "Téléchargement YouTube…");

        } else if (isDownloading && s.processing_status === "idle") {
            // Téléchargement terminé : la vidéo est prête → on peut lancer le pipeline
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
            processVideo(); // lancement automatique du pipeline

        } else if (isDownloading && s.processing_status === "error") {
            // Erreur pendant le téléchargement
            isDownloading = false;
            stopPolling();
            ytBtn.disabled = false;
            uploadBtn.disabled = false;
            uploadInfo.textContent = s.status_message || "Erreur téléchargement";
            setStatus(s.status_message || "Erreur téléchargement", "error");

        } else if (s.processing_status === "extracting") {
            // Étape 1/2 du pipeline : extraction des signaux faciaux (33% de la barre)
            processInfo.textContent = s.status_message || "Extraction des signaux…";
            processProgress.value = 33;

        } else if (s.processing_status === "mapping") {
            // Étape 2/2 du pipeline : génération du mouvement robot (66% de la barre)
            processInfo.textContent = s.status_message || "Génération du mouvement…";
            processProgress.value = 66;

        } else if (s.processing_status === "ready") {
            // Pipeline terminé : mouvement prêt, on peut jouer
            processInfo.textContent = s.status_message || "Mouvement prêt";
            processProgress.value = 100;
            stopPolling();
            processBtn.disabled = false;
            playBtn.disabled = false;
            stopBtn.disabled = true;
            setStatus("Mouvement prêt — vous pouvez lancer le rejeu", "ok");
            // Masquage de la barre de progression après 1s
            setTimeout(() => { processProgress.hidden = true; }, 1000);
            // Rafraîchissement du menu des vidéos traitées
            loadCachedVideos();

        } else if (s.processing_status === "error") {
            // Erreur pipeline : affichage du message et arrêt du polling
            processInfo.textContent = s.status_message || "Erreur lors du traitement";
            stopPolling();
            processBtn.disabled = false;
            processProgress.hidden = true;
            setStatus(s.status_message || "Erreur de traitement", "error");
        }
    } catch (e) {
        // Erreur réseau : le backend est momentanément indisponible → on ignore silencieusement
        // (le polling reprendra au prochain tick)
    }
}


// ── 7. Helpers d'état UI (playback) ──────────────────────────────────────────
// Ces trois fonctions synchronisent l'état des boutons avec la phase de rejeu.

// État "en cours" : Play caché, Pause visible, Stop activé, Seek caché
function setPlayingUI() {
    playBtn.hidden = true;
    pauseBtn.hidden = false; pauseBtn.disabled = false;
    stopBtn.disabled = false;
    seekControls.hidden = true;
}

// État "en pause" : Play caché, Pause visible (texte "Reprendre"), Stop activé, Seek visible
function setPausedUI() {
    playBtn.hidden = true;
    pauseBtn.hidden = false; pauseBtn.disabled = false;
    stopBtn.disabled = false;
    seekControls.hidden = false; // affichage des boutons seek uniquement en pause
}

// État "arrêté" : Play visible et activé, Pause caché, Stop désactivé, Seek caché
function setIdleUI() {
    playBtn.hidden = false; playBtn.disabled = false;
    pauseBtn.hidden = true;
    stopBtn.disabled = true;
    seekControls.hidden = true;
}


// ── 7b. Play ─────────────────────────────────────────────────────────────────
// POST /play → démarre le rejeu robot.
// Synchronisation vidéo : on mesure le RTT de la requête et compense
// la latence réseau (elapsed/2) pour aligner le player sur le robot.
async function play() {
    playBtn.disabled = true;
    setStatus("Démarrage du rejeu…");
    try {
        videoPlayer.currentTime = 0;
        const t0 = performance.now(); // début de la mesure du RTT
        const resp = await fetch("/play", { method: "POST" });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || "Impossible de démarrer le rejeu");
        }
        // Compensation de latence réseau : le robot a déjà commencé depuis RTT/2 ms
        const elapsed = (performance.now() - t0) / 1000; // RTT en secondes
        videoPlayer.currentTime = elapsed / 2;  // on saute en avant de RTT/2
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


// ── 7c. Stop ─────────────────────────────────────────────────────────────────
// POST /stop → arrête le rejeu robot et remet la position neutre.
// Pause aussi le player vidéo côté navigateur.
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


// ── 7d. Pause / Resume ────────────────────────────────────────────────────────
// Un seul bouton bascule entre pause et reprise (toggle).
// POST /pause ou POST /resume selon l'état courant.
// À la reprise, le backend retourne elapsed (position de reprise) →
// on synchronise videoPlayer.currentTime pour rester aligné.
async function togglePause() {
    pauseBtn.disabled = true;
    if (!isPaused) {
        // ── Mise en pause ─────────────────────────────────────────────────
        const resp = await fetch("/pause", { method: "POST" });
        if (!resp.ok) { pauseBtn.disabled = false; return; }
        videoPlayer.pause();
        isPaused = true;
        pauseBtn.textContent = "▶ Reprendre";
        setPausedUI(); // affiche les boutons seek
        setStatus("En pause", "ok");
    } else {
        // ── Reprise ───────────────────────────────────────────────────────
        const resp = await fetch("/resume", { method: "POST" });
        if (!resp.ok) { pauseBtn.disabled = false; return; }
        const data = await resp.json();
        // Synchronisation : on repositionne le player au temps exact de la reprise
        videoPlayer.currentTime = data.elapsed;
        await videoPlayer.play();
        isPaused = false;
        pauseBtn.textContent = "⏸ Pause";
        setPlayingUI();
        setStatus("Rejeu en cours (robot + vidéo)", "playing");
    }
}


// ── 7e. Seek (+/-10s) ─────────────────────────────────────────────────────────
// POST /seek avec {delta: ±10} → le backend déplace la position de ±10s.
// Retourne {elapsed: float} → on synchronise le player vidéo.
// Uniquement disponible en pause (les boutons seek sont hidden sinon).
async function seek(delta) {
    seekBackBtn.disabled = seekFwdBtn.disabled = true;
    const resp = await fetch("/seek", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ delta }),
    });
    if (resp.ok) {
        const data = await resp.json();
        // Synchronisation de la vidéo : clamp entre 0 et la durée totale
        videoPlayer.currentTime = Math.max(0, Math.min(data.elapsed, videoPlayer.duration || Infinity));
        setStatus(`Position : ${data.elapsed.toFixed(1)}s`, "ok");
    }
    seekBackBtn.disabled = seekFwdBtn.disabled = false;
}

// Quand le player vidéo se termine naturellement (hors stop robot), on remet l'UI en idle
videoPlayer.addEventListener("ended", () => {
    setStatus("Rejeu terminé", "ok");
    isPaused = false;
    setIdleUI();
});


// ── 7f. Listeners des boutons de contrôle ────────────────────────────────────
uploadBtn.addEventListener("click", uploadVideo);
ytBtn.addEventListener("click", downloadYoutube);
processBtn.addEventListener("click", processVideo);
playBtn.addEventListener("click", play);
stopBtn.addEventListener("click", stop);
pauseBtn.addEventListener("click", togglePause);
seekBackBtn.addEventListener("click", () => seek(-10));  // recule de 10s
seekFwdBtn.addEventListener("click",  () => seek(+10));  // avance de 10s


// ── 8. Mode Live ──────────────────────────────────────────────────────────────
// Références DOM du mode live
const btnModeVideo  = document.getElementById("btn-mode-video");  // bouton navigation "Vidéo"
const btnModeLive   = document.getElementById("btn-mode-live");   // bouton navigation "Live"
const viewVideo     = document.getElementById("view-video");      // conteneur vue vidéo
const viewLive      = document.getElementById("view-live");       // conteneur vue live
const liveStreamImg = document.getElementById("live-stream-img"); // <img> pour le flux MJPEG
const liveStartBtn  = document.getElementById("live-start-btn");  // bouton ▶ Démarrer
const liveStopBtn   = document.getElementById("live-stop-btn");   // bouton ⏹ Arrêter
const liveStatusMsg = document.getElementById("live-status-msg"); // texte de statut live


// Bascule entre la vue Vidéo et la vue Live.
// Passage en vidéo → arrêt du live si actif (stopLive).
function switchMode(mode) {
    if (mode === "live") {
        viewVideo.hidden = true;
        viewLive.hidden = false;
        btnModeLive.classList.add("mode-btn--active");
        btnModeVideo.classList.remove("mode-btn--active");
    } else {
        viewLive.hidden = true;
        viewVideo.hidden = false;
        btnModeVideo.classList.add("mode-btn--active");
        btnModeLive.classList.remove("mode-btn--active");
        stopLive(); // arrêt propre du live quand on quitte la vue
    }
}


// Démarre le mode live caméra.
// POST /live/start → LiveProcessor démarre (capture + calibration).
// L'image src = "/live/stream" pointe sur le générateur MJPEG de la route GET /live/stream.
async function startLive() {
    liveStartBtn.disabled = true;
    setStatus("Démarrage du live…");
    try {
        const resp = await fetch("/live/start", { method: "POST" });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || "Impossible de démarrer le live");
        }
        // Démarrage du flux MJPEG : le navigateur ouvre une connexion HTTP persistante
        liveStreamImg.src = "/live/stream";
        liveStreamImg.hidden = false;
        liveStopBtn.hidden = false;
        liveStopBtn.disabled = false;
        liveStatusMsg.textContent = "Calibration en cours…";
        setStatus("Mode live démarré", "playing");
        // Polling de la calibration jusqu'à ce qu'elle soit terminée (~1s)
        pollLiveCalibration();
    } catch (e) {
        liveStartBtn.disabled = false;
        setStatus(e.message, "error");
    }
}


// Arrête le mode live.
// POST /live/stop → LiveProcessor arrêté + robot position neutre.
// Réinitialise l'image MJPEG (src = "" coupe le flux HTTP).
async function stopLive() {
    // Guard : si le bouton stop n'est pas visible/actif, on n'arrête rien
    if (liveStopBtn.disabled && liveStopBtn.hidden) return;
    liveStopBtn.disabled = true;
    await fetch("/live/stop", { method: "POST" }).catch(() => {});
    liveStreamImg.src = "";   // coupe la connexion MJPEG (le browser ferme la requête)
    liveStreamImg.hidden = true;
    liveStopBtn.hidden = true;
    liveStartBtn.disabled = false;
    liveStatusMsg.textContent = "Mode live arrêté";
    setStatus("Live arrêté");
}


// Poll GET /live/status toutes les 300ms jusqu'à ce que la calibration soit terminée.
// Une fois calibrated=true, le robot répond aux mouvements du visage.
// Arrête le polling si is_live devient false (le live a été arrêté côté serveur).
function pollLiveCalibration() {
    const t = setInterval(async () => {
        const r = await fetch("/live/status").catch(() => null);
        if (!r || !r.ok) return;
        const d = await r.json();
        if (!d.is_live) { clearInterval(t); return; } // live arrêté → stop polling
        if (d.calibrated) {
            // Calibration terminée : le robot répond maintenant aux mouvements
            liveStatusMsg.textContent = "Live en cours";
            setStatus("Live en cours (robot actif)", "playing");
            clearInterval(t); // plus besoin de poller
        }
    }, 300);
}

// Listeners navigation modes
btnModeVideo.addEventListener("click", () => switchMode("video"));
btnModeLive.addEventListener("click",  () => switchMode("live"));
liveStartBtn.addEventListener("click", startLive);
liveStopBtn.addEventListener("click",  stopLive);


// ── 9. Initialisation ─────────────────────────────────────────────────────────
// Fonction exécutée immédiatement au chargement de la page (IIFE async).
// Synchronise l'état de l'UI avec l'état actuel du backend via GET /status.
// Utile si la page est rechargée pendant un rejeu ou après un traitement.
(async function init() {
    // Chargement de la liste des vidéos déjà traitées (menu déroulant)
    loadCachedVideos();

    try {
        const resp = await fetch("/status");
        if (!resp.ok) return;
        const s = await resp.json();

        // Si une vidéo est déjà sélectionnée côté backend, on restaure le player
        if (s.current_video) {
            currentVideo = s.current_video;
            uploadInfo.textContent = `Vidéo chargée : ${currentVideo}`;
            videoPlayer.src = `/video/${encodeURIComponent(currentVideo)}`;
            processBtn.disabled = false;
        }

        // Si un mouvement est chargé en mémoire, on active le bouton play
        if (s.frame_count > 0) {
            playBtn.disabled = false;
            processInfo.textContent = `Mouvement prêt (${s.frame_count} frames, ${s.duration.toFixed(1)}s)`;
        }

        // Restauration de l'état de pause si la page a été rechargée pendant une pause
        if (s.is_replaying && s.is_paused) {
            isPaused = true;
            pauseBtn.textContent = "▶ Reprendre";
            videoPlayer.currentTime = s.paused_elapsed || 0;
            setPausedUI();
        } else if (s.is_replaying) {
            // Rejeu en cours : on remet l'UI en état "playing" (le robot joue déjà)
            isPaused = false;
            pauseBtn.textContent = "⏸ Pause";
            setPlayingUI();
        }

        // Affichage du dernier message de statut
        if (s.status_message) setStatus(s.status_message);
    } catch (e) {
        // Backend non joignable au chargement (ex: démarrage lent)
        setStatus("Backend non joignable", "error");
    }
})();
