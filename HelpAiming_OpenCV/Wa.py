import cv2
import numpy as np
import pyautogui
from PIL import ImageGrab
from math import sqrt

SCALING = 1  # 可根据需要调整缩放比例（例如0.5表示缩小一半）

# 粉红色的RGB颜色范围
LOWER_COLOR = np.array([240, 50, 50])    # R下限，G下限，B下限
UPPER_COLOR = np.array([255, 200, 220])  # R上限，G上限，B上限

# 形态学操作内核
KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

# 判断条件
MIN_DISTANCE = 10       # 分组距离阈值
MIN_AREA = 10           # 最小区域面积

# 可视化参数
MARKER_COLOR = (0, 0, 255)   # 红色标记（BGR格式）
CONTOUR_COLOR = (0, 255, 0)  # 绿色轮廓（BGR格式）

def calculate_contour_properties(cnt):
    """计算轮廓属性（质心、顶点、区域）"""
    M = cv2.moments(cnt)
    if M["m00"] == 0:
        return None
    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])
    top_point = tuple(cnt[cnt[:, :, 1].argmin()][0])
    return {
        "area": cv2.contourArea(cnt),
        "center": (cx, cy),
        "top": top_point,
        "contour": cnt
    }

def group_contours(contour_list):
    """根据距离阈值对轮廓分组"""
    groups = []
    for contour in contour_list:
        if contour["area"] < MIN_AREA:
            continue
        matched = False
        for group in groups:
            group_center = np.mean([c["center"] for c in group], axis=0)
            distance = sqrt((contour["center"][0] - group_center[0])**2 +
                            (contour["center"][1] - group_center[1])**2)
            if distance < MIN_DISTANCE:
                group.append(contour)
                matched = True
                break
        if not matched:
            groups.append([contour])
    return groups

def detect_rings():
    """核心检测逻辑"""
    # 截取屏幕并转换为RGB数组
    screen = ImageGrab.grab()
    rgb_image = np.array(screen)

    # 应用缩放
    if SCALING != 1:
        h, w = rgb_image.shape[:2]
        new_size = (int(w * SCALING), int(h * SCALING))
        rgb_image = cv2.resize(rgb_image, new_size, interpolation=cv2.INTER_AREA)

    # 创建颜色掩膜
    mask = cv2.inRange(rgb_image, LOWER_COLOR, UPPER_COLOR)

    # 形态学处理
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, KERNEL, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, KERNEL, iterations=2)

    # 查找轮廓
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)

    # 轮廓分组与筛选
    contour_props = [calculate_contour_properties(c) for c in contours]
    contour_props = [c for c in contour_props if c is not None]
    contour_groups = group_contours(contour_props)

    valid_rings = []
    for group in contour_groups:
        combined_cnt = np.vstack([c["contour"] for c in group])
        props = calculate_contour_properties(combined_cnt)
        if props and props["area"] >= MIN_AREA:
            valid_rings.append(props)

    return valid_rings, cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)

# 主循环
while True:
    rings, frame = detect_rings()

    if rings:
        # 选择y坐标最小的顶点（屏幕最高点）
        highest_ring = min(rings, key=lambda x: x["top"][1])
        tx, ty = highest_ring["top"]

        # 坐标转换（缩放图像坐标 → 原始屏幕坐标）
        original_x = int(tx / SCALING)
        original_y = int(ty / SCALING)
        target_pos = (original_x, original_y + 2)  # 添加2像素垂直偏移

        # 在预览图上绘制信息
        cv2.drawContours(frame, [highest_ring["contour"]], -1, CONTOUR_COLOR, 2)
        cv2.circle(frame, (tx, ty), 8, MARKER_COLOR, -1)
        cv2.putText(frame, f"Screen: ({original_x}, {original_y})",
                    (tx + 10, ty + 5), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, MARKER_COLOR, 1)

        print(f"最高点坐标: {target_pos}")
    else:
        print("未检测到目标")

    cv2.imshow('Detection Preview', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cv2.destroyAllWindows()