"""Генерирует демо-кадр для README: глянцевый шар на плоском хромакее."""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 1280, 720
GREEN = (0, 168, 45)

img = Image.new("RGB", (W, H), GREEN)

# мягкая тень под шаром
shadow = Image.new("L", (W, H), 0)
d = ImageDraw.Draw(shadow)
d.ellipse((640 - 210, 470, 640 + 210, 470 + 60), fill=90)
shadow = shadow.filter(ImageFilter.GaussianBlur(16))
img = Image.composite(Image.new("RGB", (W, H), (0, 92, 26)), img, shadow)

# шар: радиальный градиент с бликом
R, cx, cy = 190, 640, 330
yy, xx = np.mgrid[0:H, 0:W]
dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / R
inside = dist <= 1.0

# свет: сверху-слева
lx, ly = cx - 70, cy - 80
sdist = np.sqrt((xx - lx) ** 2 + (yy - ly) ** 2) / (R * 1.55)
light = np.clip(1.0 - sdist, 0, 1) ** 1.6

deep = np.array([22, 16, 44], dtype=float)     # тёмная сторона (холодная)
mid = np.array([123, 57, 252], dtype=float)    # фиолетовый акцент
hot = np.array([255, 226, 196], dtype=float)   # блик

base = deep + (mid - deep) * np.clip((1.0 - dist) * 1.5, 0, 1)[..., None]
col = base + (hot - base) * (light ** 2.2)[..., None]
rim = np.clip((dist - 0.955) * 22, 0, 1)[..., None]
col = col + (np.array([248, 123, 82]) - col) * rim * 0.9

arr = np.array(img, dtype=float)
arr[inside] = col[inside]
img = Image.fromarray(arr.clip(0, 255).astype(np.uint8))

img.save("demo/plate.png")
print("demo/plate.png", img.size)
