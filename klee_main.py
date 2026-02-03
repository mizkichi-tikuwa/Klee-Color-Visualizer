# klee_main.py
import pygame
import sys
import os
from colorsys import rgb_to_hsv
from pythonosc import udp_client

# ============================================================
# 1) PATH SETUP
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.path.join(BASE_DIR, "Image")
IMAGE_MAIN_DIR = os.path.join(BASE_DIR, "Image_Main")

# txtの出力先：maxパッチと同じ階層（= BASE_DIR 直下）
TXT_OUT_DIR = BASE_DIR

# ============================================================
# 2) OSC SETUP
# ============================================================
OSC_IP = "127.0.0.1"
OSC_PORT = 8000
client = udp_client.SimpleUDPClient(OSC_IP, OSC_PORT)

# ============================================================
# 3) PYGAME INIT
# ============================================================
pygame.init()
pygame.font.init()

screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
SCREEN_W, SCREEN_H = screen.get_size()
pygame.display.set_caption("Klee Color Visualizer")

clock = pygame.time.Clock()

# ============================================================
# 4) UI SCALE
# ============================================================
UI_SCALE = min(SCREEN_W / 1440.0, SCREEN_H / 900.0)
UI_SCALE = max(0.85, min(1.35, UI_SCALE))

def s(v: int) -> int:
    return max(1, int(v * UI_SCALE))

FONT_TITLE = pygame.font.SysFont("Arial", s(32), bold=True)
FONT_BIG = pygame.font.SysFont("Arial", s(28), bold=True)
FONT_SMALL = pygame.font.SysFont("Arial", s(20))
FONT_LABEL = pygame.font.SysFont("Arial", s(20), bold=True)

# ============================================================
# 5) SMOOTHING / THRESHOLD SETTINGS
# ============================================================
SAMPLE_STEP_PX = 4
RGB_DELTA_THRESHOLD = 14
BLUR_DOWNSCALE = 12

# ============================================================
# 6) OSC RATE LIMIT SETTINGS
# ============================================================
OSC_MIN_INTERVAL_MS = 50

# ============================================================
# 7) LOAD ASSETS
# ============================================================
try:
    background_path = os.path.join(IMAGE_DIR, "back.png")
    background = pygame.image.load(background_path).convert()
    background = pygame.transform.smoothscale(background, (SCREEN_W, SCREEN_H))
except Exception as e:
    print("❌ Image/back.png が読み込めません:", e)
    sys.exit()

try:
    klee_path = os.path.join(IMAGE_MAIN_DIR, "main.jpg")
    raw_image = pygame.image.load(klee_path).convert_alpha()
except Exception as e:
    print("❌ Image_Main/main.jpg が読み込めません:", e)
    sys.exit()

# ============================================================
# 8) RESPONSIVE LAYOUT CALCULATION
# ============================================================
TOP_MARGIN = s(100)
BOTTOM_UI_RESERVED = s(300)
IMG_TO_WATCH_GAP = s(100)
FRAME_PAD = s(40)

MAX_IMG_W = int(SCREEN_W * 0.72)
MAX_IMG_H = max(120, SCREEN_H - (TOP_MARGIN + BOTTOM_UI_RESERVED))

img_w, img_h = raw_image.get_size()
aspect = img_w / img_h

new_h = min(MAX_IMG_H, int(MAX_IMG_W / aspect))
new_w = int(new_h * aspect)

if new_w > MAX_IMG_W:
    new_w = MAX_IMG_W
    new_h = int(new_w / aspect)

new_w = max(160, new_w)
new_h = max(120, new_h)

scaled_image = pygame.transform.smoothscale(raw_image, (new_w, new_h))

if BLUR_DOWNSCALE and BLUR_DOWNSCALE > 0:
    small_w = max(2, new_w // BLUR_DOWNSCALE)
    small_h = max(2, new_h // BLUR_DOWNSCALE)
    small = pygame.transform.smoothscale(scaled_image, (small_w, small_h))
    sample_image = pygame.transform.smoothscale(small, (new_w, new_h))
else:
    sample_image = scaled_image

img_x = (SCREEN_W - new_w) // 2
img_y = TOP_MARGIN

# ============================================================
# 8.5) TXT GENERATION (Hue.txt / Value.txt) BEFORE TITLE SCREEN
# ============================================================
def build_hue_histogram_from_surface(surf, step=2, min_s=0.12, min_v=0.10):
    w, h = surf.get_size()
    hist = [0] * 360
    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b, *_ = surf.get_at((x, y))
            hh, ss, vv = rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            if ss < min_s or vv < min_v:
                continue
            hi = int(hh * 360) % 360
            hist[hi] += 1
    return hist

def pick_hue_centers_by_quantiles(hist, k=9):
    total = sum(hist)
    if total <= 0:
        return [int(i * 360 / k) for i in range(k)]

    cdf = []
    acc = 0
    for v in hist:
        acc += v
        cdf.append(acc)

    centers = []
    for i in range(k):
        target = int(total * ((i + 0.5) / k))
        hi = 0
        while hi < 360 and cdf[hi] < target:
            hi += 1
        centers.append(min(359, hi))

    centers = sorted(centers)
    for i in range(1, len(centers)):
        if centers[i] == centers[i - 1]:
            centers[i] = (centers[i] + 1) % 360
    return centers

def circular_distance(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)

def build_hue_to_bin_map(centers):
    hue_map = [0] * 360
    for h in range(360):
        best_i = 0
        best_d = 10**9
        for i, c in enumerate(centers):
            d = circular_distance(h, c)
            if d < best_d:
                best_d = d
                best_i = i
        hue_map[h] = best_i
    return hue_map

def build_value_histogram_from_surface(surf, step=2, min_v=0.02):
    """
    Value(0..100)の出現頻度ヒストグラムを作る
    - min_v: 真っ黒近いところはノイズとして弾きたいなら少し上げる（0..1）
    """
    w, h = surf.get_size()
    hist = [0] * 101  # 0..100
    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b, *_ = surf.get_at((x, y))
            hh, ss, vv = rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            if vv < min_v:
                continue
            vi = int(vv * 100)
            if vi < 0:
                vi = 0
            if vi > 100:
                vi = 100
            hist[vi] += 1
    return hist

def pick_value_centers_by_quantiles(hist, k=16):
    """
    Valueの分位点で代表値をk個選ぶ（0..100）
    """
    total = sum(hist)
    if total <= 0:
        # ほぼ情報が無い場合：等間隔
        return [int(i * 100 / (k - 1)) for i in range(k)]

    cdf = []
    acc = 0
    for v in hist:
        acc += v
        cdf.append(acc)

    centers = []
    for i in range(k):
        target = int(total * ((i + 0.5) / k))
        vi = 0
        while vi < 101 and cdf[vi] < target:
            vi += 1
        centers.append(min(100, vi))

    centers = sorted(centers)

    # 代表値が重複しすぎると段階が死ぬので、近すぎるものはずらす
    for i in range(1, len(centers)):
        if centers[i] <= centers[i - 1]:
            centers[i] = min(100, centers[i - 1] + 1)

    # それでも最後が溢れたら、後ろから詰め直す
    for i in range(len(centers) - 2, -1, -1):
        if centers[i] >= centers[i + 1]:
            centers[i] = max(0, centers[i + 1] - 1)

    return centers

def build_value_to_velocity_map_100(centers, vmin=1, vmax=128):
    """
    index 0..99 のValueに対して、
    「最も近い代表center」に量子化 → その代表に対応する velocity を返す (1..128)
    """
    k = len(centers)
    if k <= 1:
        return [vmin] * 100

    # 代表段階ごとの velocity（分かりやすいよう線形）
    vel_levels = []
    for i in range(k):
        vv = vmin + int(round(i * ((vmax - vmin) / float(k - 1))))
        if vv < vmin:
            vv = vmin
        if vv > vmax:
            vv = vmax
        vel_levels.append(vv)

    # value(0..99) -> nearest center -> velocity
    out = [vmin] * 100
    for v in range(100):
        best_i = 0
        best_d = 10**9
        for i, c in enumerate(centers):
            d = abs(v - c)
            if d < best_d:
                best_d = d
                best_i = i
        out[v] = vel_levels[best_i]

    # 0は除外したいので念のため
    out = [max(vmin, min(vmax, int(x))) for x in out]
    return out

def save_as_max_table_line(values, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    line = "table " + " ".join(str(int(v)) for v in values) + "\n"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(line)

def generate_txt_files_and_notify():
    # Hue（0..8 の 360個）
    hue_hist = build_hue_histogram_from_surface(sample_image, step=2, min_s=0.12, min_v=0.10)
    hue_centers = pick_hue_centers_by_quantiles(hue_hist, k=9)
    hue_map = build_hue_to_bin_map(hue_centers)
    if len(hue_map) != 360:
        print("❌ Hue map length is not 360:", len(hue_map))
        sys.exit()
    hue_txt_path = os.path.join(TXT_OUT_DIR, "Hue.txt")
    save_as_max_table_line(hue_map, hue_txt_path)

    # Value（頻度ベース → 代表16段階 → velocity 1..128 の 100個）
    val_hist = build_value_histogram_from_surface(sample_image, step=2, min_v=0.02)
    val_centers = pick_value_centers_by_quantiles(val_hist, k=16)
    value_map = build_value_to_velocity_map_100(val_centers, vmin=1, vmax=128)
    if len(value_map) != 100:
        print("❌ Value map length is not 100:", len(value_map))
        sys.exit()
    value_txt_path = os.path.join(TXT_OUT_DIR, "Value.txt")
    save_as_max_table_line(value_map, value_txt_path)

    print("✅ Hue.txt saved:", hue_txt_path)
    print("✅ Value.txt saved:", value_txt_path)
    print("✅ Hue centers:", hue_centers)
    print("✅ Value centers:", val_centers)

    # 完了通知（1回だけ）
    try:
        client.send_message("/txt", 1)
    except Exception:
        pass

# 起動直後（Start画面を描く前）に生成して通知
generate_txt_files_and_notify()

# ============================================================
# 9) UI HELPERS
# ============================================================
def draw_button(rect, text, bg, fg):
    pygame.draw.rect(screen, bg, rect, border_radius=s(10))
    label = FONT_BIG.render(text, True, fg)
    screen.blit(
        label,
        (
            rect.x + (rect.width - label.get_width()) // 2,
            rect.y + (rect.height - label.get_height()) // 2
        )
    )

def inside_rect(rect, pos):
    x, y = pos
    return rect.x <= x <= rect.x + rect.width and rect.y <= y <= rect.y + rect.height

def draw_sound_circle(center, base_r, selected, on_color, off_color):
    cx, cy = center
    pygame.draw.circle(screen, (0, 0, 0), (cx, cy), base_r)
    if selected:
        inner_r = int(base_r * 0.86)
        color = on_color
    else:
        inner_r = int(base_r * 0.80)
        color = off_color
    pygame.draw.circle(screen, color, (cx, cy), inner_r)

def draw_sound_label(center, base_r, text):
    label = FONT_LABEL.render(text, True, (255, 255, 255))
    screen.blit(label, (center[0] - label.get_width() // 2, center[1] + base_r + s(10)))

def draw_delay_circle(center, base_r, enabled):
    pygame.draw.circle(screen, (0, 0, 0), center, base_r)
    if enabled:
        inner_r = int(base_r * 0.86)
        color = (120, 220, 120)
    else:
        inner_r = int(base_r * 0.80)
        color = (200, 120, 120)
    pygame.draw.circle(screen, color, center, inner_r)

def draw_delay_label(center, base_r, text="Delay"):
    label = FONT_LABEL.render(text, True, (255, 255, 255))
    screen.blit(label, (center[0] - label.get_width() // 2, center[1] + base_r + s(10)))

# ============================================================
# 10) STATES
# ============================================================
STATE_TITLE = 0
STATE_MAIN = 1
state = STATE_TITLE

start_rect = pygame.Rect(SCREEN_W // 2 - s(120), SCREEN_H // 2 + s(20), s(240), s(64))
exit_rect = pygame.Rect(SCREEN_W - s(150), s(20), s(130), s(52))

# ============================================================
# 11) UI PLACEMENT (Watch button etc.)
# ============================================================
WATCH_W = s(170)
WATCH_H = s(48)

watch_rect = pygame.Rect(
    SCREEN_W // 2 - WATCH_W // 2,
    img_y + new_h + s(100),
    WATCH_W,
    WATCH_H
)

watch_enabled = False
running = True

# ============================================================
# 12) SOUND MODE BUTTONS (3種類)
# ============================================================
modes = 1
last_modes_sent = None

BASE_R = s(24)
CIRCLE_GAP = s(120)

ON_YELLOW = (255, 220, 90)
OFF_YELLOW = (95, 80, 35)

WATCH_TO_CIRCLES_GAP = s(86)

circles_y = watch_rect.y + watch_rect.height + WATCH_TO_CIRCLES_GAP
circles_x0 = SCREEN_W // 2 - CIRCLE_GAP

sound1_center = (int(circles_x0 + CIRCLE_GAP * 0), int(circles_y))
sound2_center = (int(circles_x0 + CIRCLE_GAP * 1), int(circles_y))
sound3_center = (int(circles_x0 + CIRCLE_GAP * 2), int(circles_y))

CLICK_PAD = s(12)
sound1_rect = pygame.Rect(
    sound1_center[0] - BASE_R - CLICK_PAD,
    sound1_center[1] - BASE_R - CLICK_PAD,
    (BASE_R + CLICK_PAD) * 2,
    (BASE_R + CLICK_PAD) * 2
)
sound2_rect = pygame.Rect(
    sound2_center[0] - BASE_R - CLICK_PAD,
    sound2_center[1] - BASE_R - CLICK_PAD,
    (BASE_R + CLICK_PAD) * 2,
    (BASE_R + CLICK_PAD) * 2
)
sound3_rect = pygame.Rect(
    sound3_center[0] - BASE_R - CLICK_PAD,
    sound3_center[1] - BASE_R - CLICK_PAD,
    (BASE_R + CLICK_PAD) * 2,
    (BASE_R + CLICK_PAD) * 2
)

def send_modes(value: int):
    global last_modes_sent
    if last_modes_sent == value:
        return
    try:
        client.send_message("/MODES", int(value))
    except Exception:
        pass
    last_modes_sent = value

# ============================================================
# 13) TEMPO (Watch + 画像内のときだけ1)
# ============================================================
last_tempo = None

def send_tempo(value: int):
    global last_tempo
    if last_tempo == value:
        return
    try:
        client.send_message("/TEMPO", int(value))
    except Exception:
        pass
    last_tempo = value

# ============================================================
# 14) DELAY TOGGLE
# ============================================================
delay_enabled = True
last_delay_sent = None

def send_delay(value: int):
    global last_delay_sent
    if last_delay_sent == value:
        return
    try:
        client.send_message("/delay", int(value))
    except Exception:
        pass
    last_delay_sent = value

DELAY_R = s(24)
DELAY_GAP = s(120)
delay_center = (sound3_center[0] + DELAY_GAP, sound3_center[1])
delay_rect = pygame.Rect(
    delay_center[0] - (DELAY_R + CLICK_PAD),
    delay_center[1] - (DELAY_R + CLICK_PAD),
    (DELAY_R + CLICK_PAD) * 2,
    (DELAY_R + CLICK_PAD) * 2
)

# ============================================================
# 15) COLOR PANEL / OSC STATE
# ============================================================
current_color = (0, 0, 0)
show_color_panel = False
rgb_txt = (0, 0, 0)
hsv_txt = (0, 0, 0)

last_inside_active = False
last_sent_rgb = None
last_sent_hsv = None
last_color_send_ms = 0

def send_zero_color():
    global last_sent_rgb, last_sent_hsv
    try:
        client.send_message("/rgb", [0, 0, 0])
        client.send_message("/hsv", [0, 0, 0])
    except Exception:
        pass
    last_sent_rgb = (0, 0, 0)
    last_sent_hsv = (0, 0, 0)

def rgb_delta(a, b):
    return abs(a[0]-b[0]) + abs(a[1]-b[1]) + abs(a[2]-b[2])

send_delay(1 if delay_enabled else 0)

# ============================================================
# 16) MAIN LOOP
# ============================================================
while running:
    now_ms = pygame.time.get_ticks()

    mx, my = pygame.mouse.get_pos()
    inside_image = (img_x <= mx < img_x + new_w) and (img_y <= my < img_y + new_h)

    for ev in pygame.event.get():
        if ev.type == pygame.QUIT:
            send_tempo(0)
            send_zero_color()
            send_delay(0)
            running = False

        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            send_tempo(0)
            send_zero_color()
            send_delay(0)
            running = False

        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if state == STATE_TITLE:
                if inside_rect(start_rect, (mx, my)):
                    state = STATE_MAIN
                    watch_enabled = False
                    send_tempo(0)
                    send_modes(modes)
                    send_zero_color()
                    send_delay(1 if delay_enabled else 0)

            elif state == STATE_MAIN:
                if inside_rect(exit_rect, (mx, my)):
                    state = STATE_TITLE
                    watch_enabled = False
                    send_tempo(0)
                    send_zero_color()
                    send_delay(1 if delay_enabled else 0)

                if inside_rect(watch_rect, (mx, my)):
                    watch_enabled = not watch_enabled
                    if not watch_enabled:
                        send_tempo(0)
                        send_zero_color()

                if inside_rect(sound1_rect, (mx, my)):
                    modes = 1
                    send_modes(modes)
                elif inside_rect(sound2_rect, (mx, my)):
                    modes = 2
                    send_modes(modes)
                elif inside_rect(sound3_rect, (mx, my)):
                    modes = 3
                    send_modes(modes)

                if inside_rect(delay_rect, (mx, my)):
                    delay_enabled = not delay_enabled
                    send_delay(1 if delay_enabled else 0)

    send_modes(modes)
    send_delay(1 if delay_enabled else 0)

    desired_tempo = 1 if (watch_enabled and inside_image) else 0
    send_tempo(desired_tempo)

    screen.blit(background, (0, 0))

    if state == STATE_TITLE:
        overlay = pygame.Surface((SCREEN_W, SCREEN_H))
        overlay.set_alpha(150)
        overlay.fill((0, 0, 0))
        screen.blit(overlay, (0, 0))

        title = FONT_TITLE.render("Welcome to the Paul Klee exhibition", True, (255, 255, 255))
        screen.blit(title, ((SCREEN_W - title.get_width()) // 2, SCREEN_H // 2 - s(60)))
        draw_button(start_rect, "Start", (255, 255, 255), (0, 0, 0))

        pygame.display.flip()
        clock.tick(60)
        continue

    frame_surf = pygame.Surface((new_w + FRAME_PAD * 2, new_h + FRAME_PAD * 2), pygame.SRCALPHA)
    cols = ["#f0d468", "#b68a4e", "#ead26c", "#a77945", "#e2ba48"]
    offs = [0, s(5), s(10), s(20), s(30)]
    for c, o in zip(cols, offs):
        pygame.draw.rect(
            frame_surf,
            pygame.Color(c),
            (o, o, new_w + FRAME_PAD * 2 - 2 * o, new_h + FRAME_PAD * 2 - 2 * o)
        )
    screen.blit(frame_surf, (img_x - FRAME_PAD, img_y - FRAME_PAD))

    screen.blit(scaled_image, (img_x, img_y))

    if not watch_enabled:
        ov = pygame.Surface((SCREEN_W, SCREEN_H))
        ov.set_alpha(150)
        ov.fill((0, 0, 0))
        screen.blit(ov, (0, 0))

    draw_button(exit_rect, "Exit", (255, 255, 255), (0, 0, 0))
    draw_button(
        watch_rect,
        "Close" if watch_enabled else "Watch",
        (50, 50, 50) if watch_enabled else (255, 255, 255),
        (255, 255, 255) if watch_enabled else (0, 0, 0)
    )

    draw_sound_circle(sound1_center, BASE_R, modes == 1, ON_YELLOW, OFF_YELLOW)
    draw_sound_circle(sound2_center, BASE_R, modes == 2, ON_YELLOW, OFF_YELLOW)
    draw_sound_circle(sound3_center, BASE_R, modes == 3, ON_YELLOW, OFF_YELLOW)

    draw_sound_label(sound1_center, BASE_R, "Sound1")
    draw_sound_label(sound2_center, BASE_R, "Sound2")
    draw_sound_label(sound3_center, BASE_R, "Sound3")

    draw_delay_circle(delay_center, DELAY_R, delay_enabled)
    draw_delay_label(delay_center, DELAY_R, "Delay")

    active_now = (watch_enabled and inside_image)

    if active_now:
        ix = mx - img_x
        iy = my - img_y

        if SAMPLE_STEP_PX and SAMPLE_STEP_PX > 1:
            ix = (ix // SAMPLE_STEP_PX) * SAMPLE_STEP_PX
            iy = (iy // SAMPLE_STEP_PX) * SAMPLE_STEP_PX
            ix = max(0, min(new_w - 1, ix))
            iy = max(0, min(new_h - 1, iy))

        r, g, b, *_ = sample_image.get_at((ix, iy))
        sampled_rgb = (r, g, b)

        should_send = True
        if last_sent_rgb is not None:
            if rgb_delta(sampled_rgb, last_sent_rgb) < RGB_DELTA_THRESHOLD:
                should_send = False

        entered_now = (not last_inside_active) and active_now

        rate_ok = (now_ms - last_color_send_ms) >= OSC_MIN_INTERVAL_MS
        if entered_now:
            rate_ok = True

        if should_send and rate_ok:
            current_color = sampled_rgb

            h, s2, v2 = rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            h1, s1, v1 = int(h * 360), int(s2 * 100), int(v2 * 100)

            try:
                if last_sent_rgb != sampled_rgb:
                    client.send_message("/rgb", [r, g, b])
                    last_sent_rgb = sampled_rgb
                if last_sent_hsv != (h1, s1, v1):
                    client.send_message("/hsv", [h1, s1, v1])
                    last_sent_hsv = (h1, s1, v1)
            except Exception:
                pass

            last_color_send_ms = now_ms

        pygame.draw.line(screen, (255, 255, 255), (mx - s(6), my), (mx + s(6), my), s(2))
        pygame.draw.line(screen, (255, 255, 255), (mx, my - s(6)), (mx, my + s(6)), s(2))

        show_color_panel = True
        rgb_txt = last_sent_rgb if last_sent_rgb is not None else (0, 0, 0)
        hsv_txt = last_sent_hsv if last_sent_hsv is not None else (0, 0, 0)

    else:
        show_color_panel = False
        if last_inside_active:
            send_zero_color()

    last_inside_active = active_now

    if show_color_panel:
        px, py = s(20), s(20)
        pygame.draw.rect(screen, current_color, (px, py, s(120), s(120)))
        t1 = FONT_SMALL.render(f"RGB: {rgb_txt[0]}, {rgb_txt[1]}, {rgb_txt[2]}", True, (255, 255, 255))
        screen.blit(t1, (px, py + s(130)))
        t2 = FONT_SMALL.render(f"HSV: {hsv_txt[0]}°, {hsv_txt[1]}%, {hsv_txt[2]}%", True, (255, 255, 255))
        screen.blit(t2, (px, py + s(130) + t1.get_height() + s(6)))

    pygame.display.flip()
    clock.tick(60)

# ============================================================
# 17) CLEANUP
# ============================================================
send_tempo(0)
send_zero_color()
send_delay(0)
pygame.quit()
sys.exit()
