import os
import csv
import json
import math
import argparse
import cv2
import mediapipe as mp
import numpy as np

UPPER_LIP, LOWER_LIP = 13, 14
L_MOUTH, R_MOUTH     = 61, 291
L_EYE_TOP, L_EYE_BOT = 159, 145
L_EYE_L, L_EYE_R    = 33, 133
NOSE_TIP             = 1
FACE_LEFT, FACE_RIGHT = 234, 454

NAMED_LANDMARKS = {
    1: "nose_tip", 33: "left_eye_inner", 133: "left_eye_outer",
    159: "left_eye_top", 145: "left_eye_bottom", 263: "right_eye_inner",
    362: "right_eye_outer", 386: "right_eye_top", 374: "right_eye_bottom",
    13: "upper_lip", 14: "lower_lip", 61: "mouth_left", 291: "mouth_right",
    234: "face_left", 454: "face_right", 10: "forehead", 152: "chin",
}


def _dist(a, b, W, H):
    return math.hypot((a.x - b.x) * W, (a.y - b.y) * H)

def mouth_open(lm, W, H):
    h = _dist(lm[UPPER_LIP], lm[LOWER_LIP], W, H)
    w = _dist(lm[L_MOUTH], lm[R_MOUTH], W, H)
    return float(np.clip((h / w) / 0.6, 0.0, 1.0)) if w else 0.0

def left_eye_open(lm, W, H):
    ear = _dist(lm[L_EYE_TOP], lm[L_EYE_BOT], W, H) / (_dist(lm[L_EYE_L], lm[L_EYE_R], W, H) or 1)
    return float(np.clip((ear - 0.08) / 0.27, 0.0, 1.0))

def head_yaw(lm, W, H):
    ld = abs(lm[NOSE_TIP].x - lm[FACE_LEFT].x) * W
    rd = abs(lm[FACE_RIGHT].x - lm[NOSE_TIP].x) * W
    total = ld + rd
    return float(np.clip(((rd - ld) / total) * 45.0, -90.0, 90.0)) if total else 0.0

def bounding_box(lm, W, H):
    xs = [l.x * W for l in lm]
    ys = [l.y * H for l in lm]
    x, y = int(min(xs)), int(min(ys))
    return {"x": x, "y": y, "w": int(max(xs)) - x, "h": int(max(ys)) - y}


def analyse_video(video_path: str, out_csv: str, out_json: str):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Impossible d'ouvrir : {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    W   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[INFO] {W}×{H} @ {fps:.1f} FPS — {video_path}")

    csv_rows, json_frames = [], []

    face_mesh = mp.solutions.face_mesh.FaceMesh(
        max_num_faces=1, refine_landmarks=True,
        min_detection_confidence=0.5, min_tracking_confidence=0.5,
    )

    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        ts  = round(frame_idx / fps, 4)
        lm  = None
        res = face_mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

        if res.multi_face_landmarks:
            lm = res.multi_face_landmarks[0].landmark

            mo  = round(mouth_open(lm, W, H), 4)
            leo = round(left_eye_open(lm, W, H), 4)
            hy  = round(head_yaw(lm, W, H), 4)
            bb  = bounding_box(lm, W, H)

            csv_rows.append({"timestamp": ts, "mouth_open": mo, "left_eye_open": leo, "head_yaw": hy})

            json_frames.append({
                "timestamp": ts, "image_width": W, "image_height": H,
                "bounding_box": bb,
                "signals": {"mouth_open": mo, "left_eye_open": leo, "head_yaw": hy},
                "landmarks": [
                    {"id": lid, "x": round(lm[lid].x * W), "y": round(lm[lid].y * H), "label": label}
                    for lid, label in NAMED_LANDMARKS.items()
                ],
            })

        frame_idx += 1

    cap.release()
    face_mesh.close()

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "mouth_open", "left_eye_open", "head_yaw"])
        writer.writeheader()
        writer.writerows(csv_rows)

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(json_frames, f, indent=2, ensure_ascii=False)

    print(f"[OK] {len(csv_rows)} frames → {out_csv} | {out_json}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extraction signaux faciaux → CSV + JSON")
    parser.add_argument("--video", required=True)
    parser.add_argument("--csv",   default="signals.csv")
    parser.add_argument("--json",  default="frames.json")
    args = parser.parse_args()
    analyse_video(args.video, args.csv, args.json)
