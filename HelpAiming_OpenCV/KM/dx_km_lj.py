import ctypes
import os
import time
from ctypes import wintypes

import pyautogui

from KMLJ import KMLJ

# import wintypes  #  如果上面from ctypes import wintypes 找不到,就用这个代替

user32 = ctypes.windll.user32


def find_dll(dll_name):
    # 获取系统的 PATH 环境变量
    paths = os.environ.get("PATH", "").split(os.pathsep)

    # 在每个路径下查找是否有该 DLL
    for path in paths:
        potential_path = os.path.join(path, dll_name)
        if os.path.exists(potential_path):
            return os.path.abspath(potential_path)

    return None


def ChangeInputMode():
    # 加载 user32.dll 和 kernel32.dll
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

    # 常量定义
    WM_INPUTLANGCHANGEREQUEST = 0x0050
    HWND_BROADCAST = 0xFFFF
    KLF_ACTIVATE = 0x00000001
    KL_INPUTLANGCHANGE = 0x0001  # 触发输入语言更改

    # 英语（美国）的 KLID
    KLID_ENGLISH_US = "00000409"

    # 定义函数原型
    user32.LoadKeyboardLayoutW.argtypes = [wintypes.LPCWSTR, wintypes.UINT]
    user32.LoadKeyboardLayoutW.restype = wintypes.HKL

    user32.ActivateKeyboardLayout.argtypes = [wintypes.HKL, wintypes.UINT]
    user32.ActivateKeyboardLayout.restype = wintypes.HKL

    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL

    kernel32.GetLastError.restype = wintypes.DWORD
    kernel32.GetLastError.argtypes = []

    # 步骤 1: 加载英语（美国）键盘布局
    hkl_english = user32.LoadKeyboardLayoutW(KLID_ENGLISH_US, KLF_ACTIVATE)
    if not hkl_english:
        error_code = kernel32.GetLastError()
        print(f"无法加载英语（美国）输入法，错误代码: {error_code}")
        return
    else:
        print(f"已加载英语（美国）输入法，HKL: {hkl_english:#010x}")

    # 步骤 2: 激活英语（美国）键盘布局
    activated_hkl = user32.ActivateKeyboardLayout(hkl_english, KL_INPUTLANGCHANGE)
    if not activated_hkl:
        error_code = kernel32.GetLastError()
        print(f"无法激活英语（美国）输入法，错误代码: {error_code}")
    else:
        print(f"已激活英语（美国）输入法，HKL: {activated_hkl:#010x}")

    # 步骤 3: 通过消息广播请求切换输入法
    result = user32.PostMessageW(HWND_BROADCAST, WM_INPUTLANGCHANGEREQUEST, 0, hkl_english)
    if not result:
        error_code = kernel32.GetLastError()
        print(f"无法通过消息广播切换到英语（美国）输入法，错误代码: {error_code}")
    else:
        print("已通过消息广播切换到英语（美国）输入法")

    # 可选步骤: 确认当前输入法
    user32.GetKeyboardLayout.restype = wintypes.HKL
    user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
    current_hkl = user32.GetKeyboardLayout(0)
    print(f"当前活动的键盘布局 HKL: {current_hkl:#010x}")


class LogitechKMDriver:
    def __init__(self, handle=0):
        self.km = KMLJ(handle)

    def __del__(self):
        self.km.__del__()

    def set_delay(self, key_delay=0.01, mouse_delay=0.01):
        self.km.set_delay(key_delay, mouse_delay)

    # 按下鼠标按键
    def mouse_left_down(self):
        self.km.LeftDown()

    # 松开鼠标按键
    def mouse_left_up(self):
        self.km.LeftUp()

    def mouse_right_down(self):
        self.km.RightDown()

    def mouse_right_up(self):
        self.km.RightUp()

    def click_left_button(self):
        """
        鼠标左键原地点击,一般要配合绝对移动，在点击
        :return:
        """
        self.km.LeftClick()

    def click_right_button(self):
        """
        鼠标右键原地点击,一般要配合绝对移动，在点击
        :return:
        """
        self.km.RightClick()

    def key_down(self, key_char: str):
        """
        只支持a-z，0-9
        :param 按键字符: 比如"a",或者"b"，单个字符
        :return:
        """
        self.km.KeyDownChar(key_char)

    def key_up(self, key_char: str):
        """
        只支持a-z，0-9
        :param 按键字符: 比如"a",或者"b"，单个字符
        :return:
        """
        self.km.KeyUpChar(key_char)

    def press_key(self, key_char: str):
        """
        按下并抬起某个键
        只支持a-z，0-9
        :param 按键字符: 比如"a",或者"b"，单个字符
        :return:
        """
        self.km.KeyPressStr(key_char)

    def move_absolute(self, x: int, y: int):
        """
        绝对移动
        :param x: 横坐标
        :param y: 纵坐标
        :return:
        """
        self.km.MoveTo(x, y)

    def move_relative(self, x: int, y: int):
        """
        相对当前位置进行移动，可以是负数，表示相反方向
        :param x: 横坐标
        :param y: 纵坐标
        :return:
        """
        self.km.MoveR(x, y)

    def type_string(self, string: str, key_interval: float = 0.01):
        """
        :param 字符串: 只支持a-z,0-9
        :param 字符串间隔: 默认0.01秒
        :return:
        """
        self.km.KeyPressStr(string, key_interval)

    def slide(self, x1: int, y1: int, x2: int, y2: int, duration=2):
        """
        :param x1:横坐标
        :param y1: 纵坐标
        :param x2: 横坐标
        :param y2: 纵坐标
        :param 间隔: 单位秒
        :return:
        """
        self.km.slide(x1, y1, x2, y2, duration)


if __name__ == '__main__':
    ChangeInputMode()
    handle = 0  # 表示桌面窗口
    KM = LogitechKMDriver(handle)
    while True:
        print("------------------------------")
        x, y = KMLJ.GetCursorPos()
        print(f"x : {x},  y : {y}")
        time.sleep(3)
        KM.move_absolute(100, 100)
        time.sleep(2)
        # pyautogui.moveTo(100, 100)
        x, y = KMLJ.GetCursorPos()
        print(f"x : {x},  y : {y}")
        time.sleep(5)
    # KM.move_relative(100,100)
