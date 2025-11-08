import os
# --- FIX FOR NVIDIA GPU GRAY SCREEN ---
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"   # Disable GPU for MediaPipe
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"    # Hide TensorFlow logs

import cv2
import mediapipe as mp
import time
import random
import math
import pyautogui
from PyQt5 import QtWidgets, QtGui, QtCore
import threading

# Setup
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

screen_w, screen_h = pyautogui.size()
ASSETS_DIR = r'C:\Users\stsaa\Downloads\Compressed\game-20251031T192124Z-1-001\game\assets'
HIGHSCORE_FILE = 'highscore.txt'

# Camera setup (DirectShow for stability on NVIDIA systems)
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, screen_w)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, screen_h)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

cv2.namedWindow('Grab A Cookie!', cv2.WINDOW_NORMAL)
cv2.setWindowProperty('Grab A Cookie!', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
cv2.setWindowProperty('Grab A Cookie!', cv2.WND_PROP_TOPMOST, 1)

cookie_size = int(screen_h * 0.06)
fly_size = int(screen_h * 0.1)
ROUND_TIME = 30  # seconds per round

# Load Assets
cookie_images = []
for i in range(1, 8):
    path = os.path.join(ASSETS_DIR, f'cookie{i}.png')
    if os.path.exists(path):
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        img = cv2.resize(img, (cookie_size, cookie_size))
        cookie_images.append(img)

fly_frames = []
for i in range(1, 25):
    path = os.path.join(ASSETS_DIR, f'fly_{i:03}.png')
    if os.path.exists(path):
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        img = cv2.resize(img, (fly_size, fly_size))
        fly_frames.append(img)

if not fly_frames:
    print("No fly frames found.")
    fly_frames.append(cv2.imread(os.path.join(ASSETS_DIR, 'fly_001.png'), cv2.IMREAD_UNCHANGED))

# High Score
def load_highscore():
    if os.path.exists(HIGHSCORE_FILE):
        with open(HIGHSCORE_FILE, 'r') as f:
            return int(f.read().strip() or 0)
    return 0

def save_highscore(score):
    with open(HIGHSCORE_FILE, 'w') as f:
        f.write(str(score))

high_score = load_highscore()

# Helper for overlay
def overlay_image_alpha(bg, fg, x, y):
    h, w = fg.shape[:2]
    if x >= bg.shape[1] or y >= bg.shape[0]:
        return
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(bg.shape[1], x + w), min(bg.shape[0], y + h)
    fg_x1, fg_y1 = max(0, -x), max(0, -y)
    fg_x2, fg_y2 = fg_x1 + (x2 - x1), fg_y1 + (y2 - y1)
    if fg.shape[2] == 4:
        alpha = fg[fg_y1:fg_y2, fg_x1:fg_x2, 3] / 255.0
        for c in range(3):
            bg[y1:y2, x1:x2, c] = (
                alpha * fg[fg_y1:fg_y2, fg_x1:fg_x2, c]
                + (1 - alpha) * bg[y1:y2, x1:x2, c]
            )

# Cookie
class Dot:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.hover_frames = 0
        self.image = random.choice(cookie_images) if cookie_images else None
        self.radius = cookie_size // 2

    def draw(self, frame):
        if self.image is not None:
            overlay_image_alpha(frame, self.image, int(self.x - self.radius), int(self.y - self.radius))

    def is_hovered(self, bbox):
        dot_left = self.x - self.radius
        dot_right = self.x + self.radius
        dot_top = self.y - self.radius
        dot_bottom = self.y + self.radius
        return not (dot_right < bbox[0] or dot_left > bbox[2] or dot_bottom < bbox[1] or dot_top > bbox[3])

# Fly
class Bot:
    def __init__(self, x, y, speed=5.5):
        self.x = x
        self.y = y
        self.speed = speed
        self.frame_index = 0
        self.frame_timer = time.time()
        self.facing_right = False

    def move_towards(self, target_x, target_y):
        dx = target_x - self.x
        dy = target_y - self.y
        dist = math.hypot(dx, dy)
        if abs(dx) > 2:
            self.facing_right = dx > 0
        if dist < self.speed or dist == 0:
            self.x, self.y = target_x, target_y
        else:
            self.x += self.speed * (dx / dist)
            self.y += self.speed * (dy / dist)

    def get_bbox(self):
        return (self.x - fly_size // 2, self.y - fly_size // 2,
                self.x + fly_size // 2, self.y + fly_size // 2)

    def draw(self, frame):
        if time.time() - self.frame_timer > 0.035:
            self.frame_index = (self.frame_index + 1) % len(fly_frames)
            self.frame_timer = time.time()
        current_frame = fly_frames[self.frame_index]
        if self.facing_right:
            current_frame = cv2.flip(current_frame, 1)
        overlay_image_alpha(frame, current_frame, int(self.x - fly_size // 2), int(self.y - fly_size // 2))

# PyQt HUD
class HUD(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint |
                            QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setGeometry(0, 0, screen_w, screen_h)
        self.time_remaining = ROUND_TIME
        self.score = 0
        self.fly_score = 0
        self.highscore = high_score
        self.end_text = ""
        self.font_main = QtGui.QFont("Segoe Script", 50, QtGui.QFont.Bold)
        self.font_small = QtGui.QFont("Comic Sans MS", 32, QtGui.QFont.Bold)
        self.font_popup = QtGui.QFont("Comic Sans MS", 60, QtGui.QFont.Bold)
        self.show()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        bar_height = int(screen_h * 0.12)
        painter.setBrush(QtGui.QColor(250, 210, 160))
        painter.setPen(QtGui.QPen(QtGui.QColor(80, 60, 40), 4))
        painter.drawRect(0, 0, screen_w, bar_height)

        self.draw_text(painter, "Grab A Cookie!", screen_w // 2 - 250, int(bar_height * 0.75),
                       QtGui.QColor(108, 128, 200), self.font_main)
        self.draw_text(painter, f"🏆 High: {self.highscore}", 40, int(bar_height * 0.75),
                       QtGui.QColor(0, 0, 0), self.font_small)
        self.draw_text(painter, f"⏱ {int(self.time_remaining)}s", screen_w - 400, int(bar_height * 0.45),
                       QtGui.QColor(200, 30, 30), self.font_small)
        self.draw_text(painter, f"🍪 {self.score}", screen_w - 400, int(bar_height * 0.9),
                       QtGui.QColor(0, 150, 0), self.font_small)
        self.draw_text(painter, f"🪰 {self.fly_score}", screen_w - 200, int(bar_height * 0.9),
                       QtGui.QColor(50, 50, 200), self.font_small)

        if self.end_text:
            painter.setFont(self.font_popup)
            lines = self.end_text.split("\n")
            y_start = screen_h // 2 - len(lines) * 60
            for i, line in enumerate(lines):
                y_pos = y_start + i * 100
                painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0), 8))
                painter.drawText(screen_w // 2 - 400, y_pos, line)
                painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 2))
                painter.drawText(screen_w // 2 - 400, y_pos, line)

    def draw_text(self, painter, text, x, y, color, font):
        painter.setFont(font)
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0), 6))
        painter.drawText(x, y, text)
        painter.setPen(QtGui.QPen(color, 2))
        painter.drawText(x, y, text)

    def update_info(self, time_remaining, score, fly_score, highscore, end_text=""):
        self.time_remaining = time_remaining
        self.score = score
        self.fly_score = fly_score
        self.highscore = highscore
        self.end_text = end_text
        self.update()

def start_hud(shared):
    app = QtWidgets.QApplication([])
    ui = HUD()
    shared['ui'] = ui

    def update_hud():
        ui.update_info(shared['time'], shared['score'], shared['fly'], shared['highscore'], shared['end'])

    timer = QtCore.QTimer()
    timer.timeout.connect(update_hud)
    timer.start(100)
    app.exec_()

shared = {'time': ROUND_TIME, 'score': 0, 'fly': 0, 'highscore': high_score, 'end': ""}
hud_thread = threading.Thread(target=start_hud, args=(shared,), daemon=True)
hud_thread.start()

# Main Game
with mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.4, min_tracking_confidence=0.4) as hands:
    dots = []
    round_score = 0
    fly_score = 0
    start_time = time.time()
    bot = Bot(screen_w // 2, screen_h // 2)
    round_finished = False

    while True:
        if not round_finished:
            ret, frame = cap.read()
            if not ret:
                break
            frame = cv2.flip(frame, 1)
            frame = cv2.resize(frame, (screen_w, screen_h))
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb)

            # Hand detection
            hand_bounding_box = None
            if results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                x_vals = [lm.x for lm in results.multi_hand_landmarks[0].landmark]
                y_vals = [lm.y for lm in results.multi_hand_landmarks[0].landmark]
                h, w = frame.shape[:2]
                padding = 60
                hand_bounding_box = (min(x_vals)*w - padding, min(y_vals)*h - padding,
                                     max(x_vals)*w + padding, max(y_vals)*h + padding)

            current_time = time.time()
            elapsed_time = current_time - start_time
            time_remaining = max(0, ROUND_TIME - int(elapsed_time))
            bot.speed = 5.5 + (elapsed_time / 8)

            # Cookie collection
            if hand_bounding_box:
                for dot in dots[:]:
                    if dot.is_hovered(hand_bounding_box):
                        dot.hover_frames += 1
                        if dot.hover_frames > 2:
                            dots.remove(dot)
                            round_score += 1
                    else:
                        dot.hover_frames = 0

            # Fly movement
            if dots:
                closest_dot = min(dots, key=lambda d: math.hypot(d.x - bot.x, d.y - bot.y))
                bot.move_towards(closest_dot.x, closest_dot.y)
                if closest_dot.is_hovered(bot.get_bbox()):
                    dots.remove(closest_dot)
                    fly_score += 1

            while len(dots) < 3:
                dots.append(Dot(random.randint(cookie_size, screen_w - cookie_size),
                                random.randint(cookie_size + int(screen_h * 0.15), screen_h - cookie_size)))

            for dot in dots:
                dot.draw(frame)
            bot.draw(frame)

            # End of round
            if time_remaining <= 0:
                message = f"Time Finished!\nYou got {round_score} 🍪cookies!"
                if round_score > high_score:
                    high_score = round_score
                    save_highscore(high_score)
                    message += "\nNew High Score! 🎉"
                shared['end'] = message
                round_finished = True

            shared['time'] = time_remaining
            shared['score'] = round_score
            shared['fly'] = fly_score
            shared['highscore'] = high_score
            cv2.imshow('Grab A Cookie!', frame)
        else:
            key = cv2.waitKey(1) & 0xFF
            if key == ord('n'):
                round_score = 0
                fly_score = 0
                dots.clear()
                shared['end'] = ""
                start_time = time.time()
                round_finished = False
            elif key == ord('q'):
                break
            time.sleep(0.05)
            continue

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

cap.release()
cv2.destroyAllWindows()
