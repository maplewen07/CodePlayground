import ctypes
import sys
import time
import cv2
import numpy as np
from PIL import ImageGrab
import threading
from pynput.mouse import Listener as MouseListener
from dx_km_lj import LogitechKMDriver
from KMLJ import KMLJ

# 配置参数
SCALING = 1
LOWER_COLOR = np.array([240, 0, 0])
UPPER_COLOR = np.array([255, 150, 150])
MARKER_COLOR = (0, 0, 255)
KM = LogitechKMDriver(0)

# 全局控制变量
running = True
detection_enabled = True  # 新增全局检测开关

# 屏幕尺寸定义
full_screen = ImageGrab.grab()
SCREEN_WIDTH, SCREEN_HEIGHT = full_screen.size

# 中央区域定义（屏幕的1/10大小）
CENTRAL_WIDTH = SCREEN_WIDTH // 20
CENTRAL_HEIGHT = SCREEN_HEIGHT // 20
CENTRAL_LEFT = (SCREEN_WIDTH - CENTRAL_WIDTH) // 2
CENTRAL_TOP = (SCREEN_HEIGHT - CENTRAL_HEIGHT) // 2
CENTRAL_REGION = (CENTRAL_LEFT, CENTRAL_TOP,
                  CENTRAL_LEFT + CENTRAL_WIDTH, CENTRAL_TOP + CENTRAL_HEIGHT)


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


if not is_admin():
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
    sys.exit()
a'w'

def find_highest_point():
    """在中央区域进行颜色过滤找最高点"""
    screen = ImageGrab.grab(bbox=CENTRAL_REGION)
    rgb_image = np.array(screen)
    mask = cv2.inRange(rgb_image, LOWER_COLOR, UPPER_COLOR)
    y_coords, x_coords = np.where(mask == 255)

    if len(y_coords) == 0:
        return None, rgb_image

    min_idx = np.argmin(y_coords)
    tx_global = x_coords[min_idx] + CENTRAL_LEFT
    ty_global = y_coords[min_idx] + CENTRAL_TOP
    rgb_value = tuple(rgb_image[y_coords[min_idx], x_coords[min_idx]])
    return (tx_global, ty_global, rgb_value), rgb_image


def detection_loop():
    """主检测循环"""
    global running
    while running:
        if detection_enabled:  # 检测开关判断
            point, frame = find_highest_point()

            if point:
                tx, ty, rgb_value = point
                tx_scaled = int(tx / SCALING)
                ty_scaled = int(ty / SCALING)

                offsetX = tx_scaled - SCREEN_WIDTH / 2
                offsetY = ty_scaled - SCREEN_HEIGHT / 2

                nx, ny = KMLJ.GetCursorPos()
                fx = nx + offsetX
                fy = ny + offsetY
                KM.move_absolute(fx, fy)
                # KM.mouse_left_up()
                # KM.mouse_left_down()

                tx_local = tx - CENTRAL_LEFT
                ty_local = ty - CENTRAL_TOP
                cv2.circle(frame, (tx_local, ty_local), 5, MARKER_COLOR, -1)
                cv2.putText(frame, f"Target: ({tx}, {ty}) RGB: {rgb_value}",
                            (tx_local + 10, ty_local + 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, MARKER_COLOR, 2)
                print(f"目标位置: ({tx}, {ty}), RGB值: {rgb_value}")
            else:
                print("无目标")
        else:  # 检测禁用时的处理
            screen = ImageGrab.grab(bbox=CENTRAL_REGION)
            frame = np.array(screen)
            cv2.putText(frame, "Detection Disabled", (50, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        cv2.imshow('Preview', frame)
        if cv2.waitKey(1) & 0xFF == ord('}'):
            running = False
            break

    cv2.destroyAllWindows()


def on_click(x, y, button, pressed):
    """鼠标侧键控制检测开关"""
    global detection_enabled
    if pressed and button == button.x1:
        detection_enabled = not detection_enabled
        status = "ENABLED" if detection_enabled else "DISABLED"
        print(f"Detection {status}")


# 启动鼠标监听
mouse_listener = MouseListener(on_click=on_click)
mouse_listener.start()

# 运行主检测循环
detection_loop()

# 清理资源
mouse_listener.stop()
