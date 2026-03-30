import os, json, time, math, random, threading
import tkinter as tk
from collections import deque
import sys
from pathlib import Path

def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = get_base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"

SYSTEM_NAME = "Wall-E"
MODEL_BADGE = "Wall-E"

# Brutalist Palette (NO PURPLE)
C_BG     = "#000000"
C_PRI    = "#00d4ff" # Cyan Primary
C_MID    = "#005a77"
C_DIM    = "#002b36"
C_ACC    = "#ffae00" # Warning Orange
C_SYS    = "#00ff88" # Acid Green
C_TEXT   = "#e0e0e0"
C_PANEL  = "#050505"
C_RED    = "#ff3333"

class WallEUI:
    def __init__(self, face_path=None, size=None):
        self.root = tk.Tk()
        self.root.title("Wall-E - CLASSIFIED")
        self.root.resizable(False, False)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        W  = min(sw, 1024)
        H  = min(sh, 768)
        self.root.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")
        self.root.configure(bg=C_BG)

        self.W = W
        self.H = H

        self.speaking     = False
        self.scale        = 1.0
        self.target_scale = 1.0
        self.halo_a       = 60.0
        self.target_halo  = 60.0
        self.last_t       = time.time()
        self.tick         = 0
        
        self.glitch_offset_x = 0
        self.glitch_offset_y = 0
        
        self.bar_heights = [10] * 16

        self.status_text  = "INITIALISING"
        self.status_blink = True

        self.typing_queue = deque()
        self.is_typing    = False

        self.bg = tk.Canvas(self.root, width=W, height=H,
                            bg=C_BG, highlightthickness=0)
        self.bg.place(x=0, y=0)

        # Right side log frame (asymmetrical layout, sharp edges)
        LW = int(W * 0.45)
        LH = int(H * 0.6)
        self.log_frame = tk.Frame(self.root, bg=C_PANEL,
                                  highlightbackground=C_PRI,
                                  highlightcolor=C_PRI,
                                  highlightthickness=2) # Sharp 2px border
        self.log_frame.place(x=W - LW - 20, y=H - LH - 60, width=LW, height=LH)
        self.log_text = tk.Text(self.log_frame, fg=C_TEXT, bg=C_PANEL,
                                insertbackground=C_PRI, borderwidth=0,
                                wrap="word", font=("Courier", 10, "bold"), padx=16, pady=16)
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")
        self.log_text.tag_config("you", foreground="#ffffff")
        self.log_text.tag_config("ai",  foreground=C_PRI)
        self.log_text.tag_config("sys", foreground=C_SYS)

        self._api_key_ready = self._api_keys_exist()
        if not self._api_key_ready:
            self._show_setup_ui()

        self._animate()
        self.root.protocol("WM_DELETE_WINDOW", lambda: os._exit(0))

    @staticmethod
    def _ac(r, g, b, a):
        f = a / 255.0
        return f"#{int(r*f):02x}{int(g*f):02x}{int(b*f):02x}"

    def _animate(self):
        self.tick += 1
        t   = self.tick
        now = time.time()

        if now - self.last_t > (0.1 if self.speaking else 0.4):
            if self.speaking:
                self.target_scale = random.uniform(1.2, 1.8)
                self.target_halo  = random.uniform(150, 255)
                # Intense glitch effect when speaking
                if random.random() > 0.6:
                    self.glitch_offset_x = random.randint(-15, 15)
                    self.glitch_offset_y = random.randint(-10, 10)
                else:
                    self.glitch_offset_x = 0
                    self.glitch_offset_y = 0
            else:
                self.target_scale = random.uniform(0.9, 1.1)
                self.target_halo  = random.uniform(40, 80)
                self.glitch_offset_x = 0
                self.glitch_offset_y = 0
            self.last_t = now
            
            # Animate brutalist bars for the "Face"
            for i in range(16):
                if self.speaking:
                    self.bar_heights[i] = random.randint(20, 300)
                else:
                    self.bar_heights[i] = random.randint(10, 50 + abs(int(math.sin(t*0.1 + i)*20)))

        sp = 0.5 if self.speaking else 0.15
        self.scale  += (self.target_scale - self.scale) * sp
        self.halo_a += (self.target_halo  - self.halo_a) * sp

        if t % 30 == 0:
            self.status_blink = not self.status_blink

        self._draw()
        self.root.after(16, self._animate)

    def _draw(self):
        c    = self.bg
        W, H = self.W, self.H
        c.delete("all")

        # Technical Grid Background
        for x in range(0, W, 40):
            c.create_line(x, 0, x, H, fill="#0a0a0a", width=1)
        for y in range(0, H, 40):
            c.create_line(0, y, W, y, fill="#0a0a0a", width=1)

        # Crosshairs and alignment marks (Brutalist aesthetic)
        c.create_line(30, 30, 50, 30, fill=C_DIM, width=2)
        c.create_line(30, 30, 30, 50, fill=C_DIM, width=2)
        
        c.create_line(W-30, 30, W-50, 30, fill=C_DIM, width=2)
        c.create_line(W-30, 30, W-30, 50, fill=C_DIM, width=2)

        # Left Asymmetrical Geometric Face
        FACE_X = int(W * 0.25)
        FACE_Y = int(H * 0.45)
        
        gx = self.glitch_offset_x
        gy = self.glitch_offset_y
        
        # Wall-E Animated Geometric Face
        is_blinking = (self.tick % 160 < 12)
        base_w = int(100 * self.scale)
        base_h = int(80 * self.scale)
        
        # Speak animation: tilt eyes and bounce
        spk_bounce = math.sin(self.tick * 0.4) * 8 if self.speaking else 0
        gap = 25
        
        # Left and Right eye bounds
        lx = FACE_X - base_w - gap // 2 + gx
        ly = FACE_Y - base_h // 2 + gy + int(spk_bounce)
        
        rx = FACE_X + gap // 2 + gx
        ry = FACE_Y - base_h // 2 + gy + int(spk_bounce)
        
        pupil_color = C_ACC if self.speaking else C_PRI
        pupil_size  = int(36 * self.scale * (1.15 if self.speaking else 1.0))
        
        # Wall-E's eyes tilt up in the middle when speaking (excited), down when neutral
        inner_y_offset = -15 if self.speaking else 15
        
        # Heights for blinking
        poly_h = 10 if is_blinking else base_h
        ly_top = ly + (base_h // 2 - 5) if is_blinking else ly
        ry_top = ry + (base_h // 2 - 5) if is_blinking else ry
        
        l_poly = [
            lx, ly_top, 
            lx + base_w, ly_top + inner_y_offset, 
            lx + base_w, ly_top + poly_h + inner_y_offset, 
            lx, ly_top + poly_h
        ]
        
        r_poly = [
            rx, ry_top + inner_y_offset,
            rx + base_w, ry_top,
            rx + base_w, ry_top + poly_h,
            rx, ry_top + poly_h + inner_y_offset
        ]
        
        bg_opacity = int(self.halo_a * 0.25)
        eye_bg = self._ac(0, 212, 255, bg_opacity)
        
        # Draw eye enclosures
        c.create_polygon(l_poly, outline=C_PRI, fill=eye_bg, width=3)
        c.create_polygon(r_poly, outline=C_PRI, fill=eye_bg, width=3)
        
        # Mechanical connecting line
        c.create_line(lx + base_w, ly + base_h // 2 + inner_y_offset, 
                      rx, ry + base_h // 2 + inner_y_offset, 
                      fill=C_DIM, width=4)
        
        # Draw pupils
        if not is_blinking:
            px_shift = int(math.sin(self.tick * 0.6) * 12) if self.speaking else 0
            
            # Left pupil
            l_cx = lx + base_w // 2 + px_shift
            l_cy = ly + base_h // 2 + inner_y_offset // 2
            c.create_rectangle(l_cx - pupil_size//2, l_cy - pupil_size//2,
                               l_cx + pupil_size//2, l_cy + pupil_size//2,
                               fill=pupil_color, outline="")
             
            # Right pupil                  
            r_cx = rx + base_w // 2 + px_shift
            r_cy = ry + base_h // 2 + inner_y_offset // 2
            c.create_rectangle(r_cx - pupil_size//2, r_cy - pupil_size//2,
                               r_cx + pupil_size//2, r_cy + pupil_size//2,
                               fill=pupil_color, outline="")
                               
            if self.speaking and random.random() > 0.8:
                c.create_rectangle(l_cx - pupil_size//2 - 10, l_cy - pupil_size//2,
                                   l_cx - pupil_size//2 - 4, l_cy + pupil_size//2,
                                   fill=C_RED, outline="")
                c.create_rectangle(r_cx - pupil_size//2 - 10, r_cy - pupil_size//2,
                                   r_cx - pupil_size//2 - 4, r_cy + pupil_size//2,
                                   fill=C_RED, outline="")

        # Encasing sharp polygon
        poly_pts = [
            FACE_X - 180 + gx, FACE_Y - 180 + gy,
            FACE_X + 130 + gx, FACE_Y - 180 + gy,
            FACE_X + 180 + gx, FACE_Y - 130 + gy,
            FACE_X + 180 + gx, FACE_Y + 180 + gy,
            FACE_X - 130 + gx, FACE_Y + 180 + gy,
            FACE_X - 180 + gx, FACE_Y + 130 + gy
        ]
        alpha_hex = max(0, min(255, int(self.halo_a)))
        poly_col = self._ac(0, 212, 255, alpha_hex)
        c.create_polygon(poly_pts, outline=poly_col, fill="", width=3)
        
        # Inner smaller poly
        poly_pts_inner = [
            FACE_X - 160 + gx, FACE_Y - 160 + gy,
            FACE_X + 110 + gx, FACE_Y - 160 + gy,
            FACE_X + 160 + gx, FACE_Y - 110 + gy,
            FACE_X + 160 + gx, FACE_Y + 160 + gy,
            FACE_X - 110 + gx, FACE_Y + 160 + gy,
            FACE_X - 160 + gx, FACE_Y + 110 + gy
        ]
        c.create_polygon(poly_pts_inner, outline=C_DIM, fill="", width=1)

        # Animated Mouth
        mouth_y = FACE_Y + 70 + gy
        if self.speaking:
            # Speaking: Dynamic amplitude, opens and closes
            amp = random.randint(5, 20)
            c.create_rectangle(FACE_X - 40 + gx, mouth_y - amp, 
                               FACE_X + 40 + gx, mouth_y + amp, 
                               fill=C_ACC if random.random() > 0.5 else C_PRI, outline="")
        elif self.status_text in ["PROCESSING", "RESPONDING"]:
            # Thinking: processing wave
            wave_w = int(20 + math.sin(self.tick * 0.2) * 20)
            c.create_line(FACE_X - wave_w + gx, mouth_y, 
                          FACE_X + wave_w + gx, mouth_y, 
                          fill=C_PRI, width=4)
            if self.tick % 20 < 10:
                c.create_rectangle(FACE_X - wave_w - 15 + gx, mouth_y - 2, 
                                   FACE_X - wave_w - 10 + gx, mouth_y + 2, fill=C_PRI, outline="")
                c.create_rectangle(FACE_X + wave_w + 10 + gx, mouth_y - 2, 
                                   FACE_X + wave_w + 15 + gx, mouth_y + 2, fill=C_PRI, outline="")
        elif self.status_text == "EXECUTING":
            # Command Executing: Rapid flickering wide bar
            if self.tick % 4 < 2:
                c.create_rectangle(FACE_X - 50 + gx, mouth_y - 4, 
                                   FACE_X + 50 + gx, mouth_y + 4, 
                                   fill=C_SYS, outline="")
        else:
            # Listening / Standby: Calm cyan line, slightly pulsating width
            listen_w = 30 + int(math.sin(self.tick * 0.05) * 10)
            c.create_line(FACE_X - listen_w + gx, mouth_y, 
                          FACE_X + listen_w + gx, mouth_y, 
                          fill=C_PRI, width=3)

        # Brutalist Title (Top Right)
        title_x = W - 20
        title_y = 60
        c.create_rectangle(title_x - 380, title_y - 40, title_x, title_y + 10, fill=C_PRI, outline="")
        c.create_text(title_x - 10, title_y - 15, text="SYSTEM // WALL-E",
                      fill=C_BG, font=("Helvetica", 24, "bold"), anchor="e")
        
        # Status Block (Right)
        status_y = title_y + 40
        if self.speaking:
            stat_txt = "SPEAKING_MODE_ACTIVE"
            stat_col = C_ACC
            bg_col   = "#331100"
        elif self.status_text == "PROCESSING" or self.status_text == "RESPONDING":
            stat_txt = "THINKING_IN_PROGRESS"
            stat_col = C_PRI
            bg_col   = "#001b22"
        elif self.status_text == "EXECUTING":
            stat_txt = "EXECUTING_COMMAND"
            stat_col = C_SYS
            bg_col   = "#002211"
        else:
            stat_txt = "LISTENING_STANDBY" if self.status_blink else ""
            stat_col = C_PRI
            bg_col   = C_DIM
            
        c.create_rectangle(title_x - 260, status_y, title_x, status_y + 40, fill=bg_col, outline=stat_col, width=2)
        c.create_rectangle(title_x - 260, status_y, title_x - 240, status_y + 40, fill=stat_col, outline="")
        c.create_text(title_x - 10, status_y + 20, text=stat_txt,
                      fill=stat_col, font=("Courier", 14, "bold"), anchor="e")

        # Memory / System metrics visualization (Left Bottom)
        for i in range(5):
            mw = random.randint(20, 100) if self.speaking else 80
            my = H - 80 - (i * 15)
            c.create_rectangle(30, my, 30 + mw, my + 8, fill=C_MID, outline="")
        c.create_text(30, H - 40, text="MEMORY_PTR: OK", fill=C_MID, font=("Courier", 8), anchor="w")

        # Footer Header
        c.create_rectangle(0, H - 24, W, H, fill=C_PRI, outline="")
        c.create_text(20, H - 12, fill=C_BG, font=("Courier", 10, "bold"), anchor="w",
                      text="AHMADTCHNOLOGY INDUSTRIES  //  CLASSIFIED  //  DIR: WALL-E  //  SEC: OMEGA")

    def write_log(self, text: str):
        tl = text.lower()
        if tl.startswith("you:"):
            self.status_text = "PROCESSING"
            tag = "you"
            clean_text = text[4:].strip()
        elif tl.startswith("ai:") or tl.startswith("wall-e:"):
            self.status_text = "RESPONDING"
            tag = "ai"
            clean_text = text[7:].strip()
        else:
            self.status_text = "EXECUTING"
            tag = "sys"
            clean_text = text
            
        self.typing_queue.append((clean_text, tag, True))
        if not self.is_typing:
            self._start_typing()

    def append_log(self, text: str):
        self.typing_queue.append((text, "ai", False))
        self.status_text = "RESPONDING"
        if not self.is_typing:
            self._start_typing()

    def _start_typing(self):
        if not self.typing_queue:
            self.is_typing = False
            if not self.speaking:
                self.status_text = "ONLINE"
            return
            
        self.is_typing = True
        text, tag, needs_prefix = self.typing_queue.popleft()
        
        self.log_text.configure(state="normal")
        if needs_prefix:
            prefix = "\n> " if tag == "you" else "\n>> " if tag == "ai" else "\n-- "
            if self.log_text.get("1.0", tk.END).strip():
                # Avoid double newline at the very beginning
                pass
            self.log_text.insert(tk.END, prefix, tag)
            
        self._type_char(text, 0, tag)

    def _type_char(self, text, i, tag):
        if i < len(text):
            self.log_text.insert(tk.END, text[i], tag)
            self.log_text.see(tk.END)
            # Faster typing for brutalist tech feel
            self.root.after(4, self._type_char, text, i + 1, tag)
        else:
            self.log_text.configure(state="disabled")
            self.root.after(10, self._start_typing)

    def start_speaking(self):
        self.speaking    = True
        self.status_text = "SPEAKING"

    def stop_speaking(self):
        self.speaking    = False
        self.status_text = "ONLINE"

    def _api_keys_exist(self):
        if not API_FILE.exists():
            return False
        try:
            with open(API_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                key = data.get("gemini_api_key", "").strip()
                return bool(key)
        except Exception:
            return False

    def wait_for_api_key(self):
        while not self._api_key_ready:
            time.sleep(0.1)

    def _show_setup_ui(self):
        self.setup_frame = tk.Frame(
            self.root, bg=C_BG,
            highlightbackground=C_ACC, highlightcolor=C_ACC, highlightthickness=3
        )
        self.setup_frame.place(relx=0.5, rely=0.5, anchor="center", width=500, height=250)

        tk.Label(self.setup_frame, text="WARNING: INITIALISATION REQUIRED",
                 fg=C_ACC, bg=C_BG, font=("Helvetica", 16, "bold")).pack(pady=(20, 10))
        tk.Label(self.setup_frame,
                 text="ENTER GEMINI API KEY TO AUTHENTICATE",
                 fg=C_PRI, bg=C_BG, font=("Courier", 10, "bold")).pack(pady=(0, 20))

        self.gemini_entry = tk.Entry(
            self.setup_frame, width=50, fg=C_BG, bg=C_PRI,
            insertbackground=C_BG, borderwidth=0, font=("Courier", 12, "bold"), show="*"
        )
        self.gemini_entry.pack(pady=(0, 20), ipady=5)

        tk.Button(
            self.setup_frame, text="[ AUTHENTICATE ]",
            command=self._save_api_keys, bg=C_ACC, fg=C_BG,
            activebackground=C_PRI, activeforeground=C_BG, font=("Helvetica", 14, "bold"),
            borderwidth=0, cursor="hand2"
        ).pack(pady=10, ipadx=20)

    def _save_api_keys(self):
        gemini = self.gemini_entry.get().strip()
        if not gemini:
            return
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(API_FILE, "w", encoding="utf-8") as f:
            json.dump({"gemini_api_key": gemini}, f, indent=4)
        self.setup_frame.destroy()
        self._api_key_ready = True
        self.status_text = "ONLINE"
        self.write_log("SYS: Authentication successful. Wall-E online.")