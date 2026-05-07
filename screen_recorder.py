import os
import threading
import queue
import time
import wave
from dataclasses import dataclass
from datetime import datetime

import cv2
import mss
import numpy as np
import sounddevice as sd
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import keyboard
import pyautogui


@dataclass
class RecorderConfig:
    fps: int = 30
    sample_rate: int = 48000
    channels: int = 1
    zoom_factor: float = 2.0


class ScreenRecorderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("高清录屏助手")
        self.root.geometry("520x360")

        self.config = RecorderConfig()
        self.is_recording = False
        self.stop_event = threading.Event()

        self.audio_queue = queue.Queue()
        self.audio_frames = []
        self.video_writer = None
        self.record_thread = None
        self.audio_stream = None

        self.output_dir = os.path.abspath("./recordings")
        os.makedirs(self.output_dir, exist_ok=True)

        self._build_ui()
        self._start_waveform_updater()

    def _build_ui(self):
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="保存目录：").pack(anchor="w")
        dir_row = ttk.Frame(frame)
        dir_row.pack(fill="x", pady=(4, 10))
        self.dir_var = tk.StringVar(value=self.output_dir)
        ttk.Entry(dir_row, textvariable=self.dir_var).pack(side="left", fill="x", expand=True)
        ttk.Button(dir_row, text="选择", command=self.choose_dir).pack(side="left", padx=6)

        cfg_row = ttk.Frame(frame)
        cfg_row.pack(fill="x", pady=(0, 12))

        ttk.Label(cfg_row, text="FPS").grid(row=0, column=0, sticky="w")
        self.fps_var = tk.IntVar(value=30)
        ttk.Spinbox(cfg_row, from_=15, to=60, textvariable=self.fps_var, width=8).grid(row=0, column=1, padx=(4, 20))

        ttk.Label(cfg_row, text="分辨率").grid(row=0, column=2, sticky="w")
        self.res_var = tk.StringVar(value="屏幕原始分辨率")
        ttk.Label(cfg_row, textvariable=self.res_var).grid(row=0, column=3, sticky="w")

        self.status_var = tk.StringVar(value="状态：未录制")
        ttk.Label(frame, textvariable=self.status_var).pack(anchor="w")

        ttk.Label(frame, text="音频声浪（用于检测声音是否录入）：").pack(anchor="w", pady=(12, 4))
        self.wave_canvas = tk.Canvas(frame, width=480, height=90, bg="#0f172a", highlightthickness=0)
        self.wave_canvas.pack(fill="x")

        hint_text = (
            "快捷功能：\n"
            "• 按住 Alt：放大画面（跟随鼠标）\n"
            "• 按住 Ctrl：鼠标高亮为红色，便于引导视线"
        )
        ttk.Label(frame, text=hint_text).pack(anchor="w", pady=(10, 12))

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill="x")
        self.start_btn = ttk.Button(btn_row, text="开始录制", command=self.start_recording)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(btn_row, text="停止录制", command=self.stop_recording, state="disabled")
        self.stop_btn.pack(side="left", padx=8)

    def choose_dir(self):
        selected = filedialog.askdirectory(initialdir=self.output_dir)
        if selected:
            self.output_dir = selected
            self.dir_var.set(selected)

    def _start_waveform_updater(self):
        self.latest_level = 0

        def update():
            self.wave_canvas.delete("all")
            w = self.wave_canvas.winfo_width() or 480
            h = self.wave_canvas.winfo_height() or 90
            center_y = h // 2
            level = int(self.latest_level * (h // 2 - 8))
            self.wave_canvas.create_line(0, center_y, w, center_y, fill="#334155", width=1)
            if level > 0:
                self.wave_canvas.create_rectangle(0, center_y - level, w, center_y + level, fill="#22d3ee", outline="")
            self.root.after(33, update)

        update()

    def audio_callback(self, indata, frames, time_info, status):
        if status:
            print(status)
        mono = indata[:, 0].copy()
        self.audio_frames.append(mono)
        rms = float(np.sqrt(np.mean(np.square(mono))))
        self.latest_level = min(rms * 8, 1.0)

    def start_recording(self):
        if self.is_recording:
            return

        self.config.fps = int(self.fps_var.get())
        self.output_dir = self.dir_var.get().strip() or self.output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.video_path = os.path.join(self.output_dir, f"record_{self.timestamp}.mp4")
        self.audio_path = os.path.join(self.output_dir, f"record_{self.timestamp}.wav")

        with mss.mss() as sct:
            mon = sct.monitors[1]
            self.monitor = {"top": mon["top"], "left": mon["left"], "width": mon["width"], "height": mon["height"]}
            self.res_var.set(f"{mon['width']}x{mon['height']}")

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.video_writer = cv2.VideoWriter(self.video_path, fourcc, self.config.fps, (self.monitor["width"], self.monitor["height"]))

        self.audio_frames = []
        self.stop_event.clear()
        self.audio_stream = sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype="float32",
            callback=self.audio_callback,
        )
        self.audio_stream.start()

        self.record_thread = threading.Thread(target=self._record_screen_loop, daemon=True)
        self.record_thread.start()

        self.is_recording = True
        self.status_var.set("状态：录制中")
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

    def _record_screen_loop(self):
        frame_interval = 1.0 / self.config.fps
        with mss.mss() as sct:
            while not self.stop_event.is_set():
                t0 = time.time()
                raw = np.array(sct.grab(self.monitor))
                frame = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)

                mx, my = pyautogui.position()
                local_x = int(mx - self.monitor["left"])
                local_y = int(my - self.monitor["top"])

                if keyboard.is_pressed("alt"):
                    frame = self._apply_zoom(frame, local_x, local_y)

                if keyboard.is_pressed("ctrl"):
                    cv2.circle(frame, (local_x, local_y), 18, (0, 0, 255), 3)
                    cv2.circle(frame, (local_x, local_y), 4, (0, 0, 255), -1)

                self.video_writer.write(frame)

                elapsed = time.time() - t0
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

    def _apply_zoom(self, frame, cx, cy):
        h, w = frame.shape[:2]
        crop_w = int(w / self.config.zoom_factor)
        crop_h = int(h / self.config.zoom_factor)

        x1 = max(0, min(cx - crop_w // 2, w - crop_w))
        y1 = max(0, min(cy - crop_h // 2, h - crop_h))
        crop = frame[y1:y1 + crop_h, x1:x1 + crop_w]
        zoomed = cv2.resize(crop, (w, h), interpolation=cv2.INTER_LINEAR)
        return zoomed

    def stop_recording(self):
        if not self.is_recording:
            return

        self.stop_event.set()
        if self.record_thread:
            self.record_thread.join(timeout=3)

        if self.audio_stream:
            self.audio_stream.stop()
            self.audio_stream.close()

        if self.video_writer:
            self.video_writer.release()

        self._save_audio_wav()
        self.is_recording = False

        self.status_var.set(f"状态：已保存\n视频：{self.video_path}\n音频：{self.audio_path}")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        messagebox.showinfo("录制完成", f"文件已保存到：\n{self.video_path}\n{self.audio_path}")

    def _save_audio_wav(self):
        if not self.audio_frames:
            return
        data = np.concatenate(self.audio_frames)
        pcm16 = np.int16(np.clip(data, -1.0, 1.0) * 32767)
        with wave.open(self.audio_path, "wb") as wf:
            wf.setnchannels(self.config.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.config.sample_rate)
            wf.writeframes(pcm16.tobytes())


if __name__ == "__main__":
    root = tk.Tk()
    app = ScreenRecorderApp(root)
    root.mainloop()
