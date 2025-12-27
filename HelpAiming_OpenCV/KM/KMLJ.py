import ctypes
import os
import sys
import time
import ctypes.wintypes

user32 = ctypes.windll.user32


def ClientToScreen(hwnd, x, y) -> tuple:
    point = ctypes.wintypes.POINT()
    point.x = x
    point.y = y
    is_ok: bool = user32.ClientToScreen(hwnd, ctypes.byref(point))
    if not is_ok:
        raise Exception('call ClientToScreen failed')
    return point.x, point.y


class KMLJ:
    keys = [
        "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
        "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
        "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"
    ]
    shift_keys = {
        "!": "1",
        "@": "2",
        "#": "3",
        "$": "4",
        "%": "5",
        "^": "6",
        "&": "7",
        "*": "8",
        "(": "9",
        ")": "0"
    }

    vk_key_map = {
        'shift': 0x10,
        'ctrl': 0x11,
        'alt': 0x12,
        ':capslock': 0x14,
        'tab': 0x09,
        'enter': 0x0D,
        'esc': 0x1B,
        'space': 0x20,
        'backspace': 0x08,
    }
    gm = None

    def __init__(self, hwnd=0):
        if not sys.maxsize > 2 ** 32:
            raise ValueError('KMLJ不支持32,请使用64位python!!!')

        self.hwnd = hwnd

        device_path = os.path.join(os.path.dirname(__file__), "km_lj.dll")
        if not device_path:
            raise ValueError(f"找不到 {device_path}")
        try:
            if KMLJ.gm is None:
                self.gm = ctypes.CDLL(device_path)
                self.gm.device_close()
                self.gmok = self.gm.device_open() == 1
                if not self.gmok:
                    raise ValueError('未安装ghub或者lgs驱动!!!')
                else:
                    print('初始化成功!')
            else:
                self.gm = KMLJ.gm
        except FileNotFoundError:
            raise ValueError('缺少文件!!!')
        self.init_mouse()
        self.init_keypress()
        self.now_x, self.now_y = self.GetCursorPos()
        self.key_delay = 0.01
        self.mouse_delay = 0.01
        self.all_up()

    def __del__(self):
        self.all_up()

    def all_up(self):
        for key in self.keys:
            self.KeyUpChar(key)
        self.LeftUp()
        self.RightUp()

    def release(self):
        self.init_mouse()
        self.init_keypress()

    def init_mouse(self):
        self.LeftUp()
        self.RightUp()

    def init_keypress(self):
        for key in self.keys:
            self.KeyUpChar(key)

    def set_delay(self, key_delay=0.01, mouse_delay=0.01):
        self.key_delay = key_delay
        self.mouse_delay = mouse_delay

    # 按下鼠标按键
    def LeftDown(self):
        self.gm.mouse_down(1)

    # 松开鼠标按键
    def LeftUp(self):
        self.gm.mouse_up(1)

    def RightDown(self):
        self.gm.mouse_down(3)

    def RightUp(self):
        self.gm.mouse_up(3)

    def LeftClick(self):
        self.LeftDown()
        time.sleep(self.mouse_delay)
        self.LeftUp()

    def RightClick(self):
        self.RightDown()
        time.sleep(self.mouse_delay)
        self.RightUp()

    def KeyDownChar(self, code: str):
        if code.isupper():
            code = code.lower()
            self.press_capslock(True)
        else:
            self.press_capslock(False)
        if code in self.shift_keys:
            self.press_controller_down("shift")
            self.gm.key_down(self.shift_keys[code])

        self.gm.key_down(code)

    def KeyUpChar(self, code: str):
        if code.isupper():
            code = code.lower()
        self.gm.key_up(code)
        if code in self.shift_keys:  # 弹起特殊操控键
            self.press_controller_up("shift")

    def KeyPressChar(self, code: str):
        self.KeyDownChar(code)
        time.sleep(self.key_delay)
        self.KeyUpChar(code)

    def MoveTo(self, x: int, y: int):
        self.now_x, self.now_y = self.GetCursorPos()
        if self.hwnd:
            x, y = ClientToScreen(self.hwnd, x, y)
        self.MoveR(x - self.now_x, y - self.now_y)

    def MoveR(self, x: int, y: int):
        x /= 3.5
        y /= 3.5
        self.gm.moveR(int(x), int(y), False)
        self.now_x, self.now_y = self.now_x + x, self.now_y + y

    def KeyPressStr(self, key_str: str, delay: float = 0.01):
        for i in key_str:
            self.KeyPressChar(i)
            time.sleep(delay)

    def slide(self, x1: int, y1: int, x2: int, y2: int, delay=1):
        self.MoveTo(x1, y1)
        time.sleep(0.01)
        self.LeftDown()
        time.sleep(0.01)
        self.MoveR(x2 - x1, y2 - y1)
        self.LeftUp()
        time.sleep(delay)

    @staticmethod
    def GetCursorPos():
        class POINT(ctypes.Structure):
            _fields_ = [
                ("x", ctypes.c_long),
                ("y", ctypes.c_long)
            ]

        point = POINT()
        user32.GetCursorPos(ctypes.byref(point))
        return point.x, point.y

    # 模拟按下 Caps Lock 键
    def press_capslock(self, open=True):
        if open:
            if not user32.GetKeyState(self.vk_key_map[":capslock"]) & 1:
                self.press_controller_key(":capslock")
        else:
            if user32.GetKeyState(self.vk_key_map[":capslock"]) & 1:
                self.press_controller_key(":capslock")

    def press_controller_key(self, key):
        self.press_controller_down(key)
        time.sleep(self.key_delay)
        self.press_controller_up(key)

    def press_controller_down(self, key):
        if not key in self.vk_key_map:
            raise ValueError("无效的按键")
        user32.keybd_event(self.vk_key_map[key], 0, 0, 0)

    def press_controller_up(self, key):
        if not key in self.vk_key_map:
            raise ValueError("无效的按键")
        # 模拟释放 Caps Lock
        user32.keybd_event(self.vk_key_map[key], 0, 2, 0)
