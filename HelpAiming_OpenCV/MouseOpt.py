import ctypes
import numpy as np


class MouseState(ctypes.Structure):  # 鼠标监听状态
    _fields_ = [
        ("leftButtonDown", ctypes.c_int),
        ("rightButtonDown", ctypes.c_int),
        ("middleButtonDown", ctypes.c_int),
        ("x1ButtonDown", ctypes.c_int),
        ("x2ButtonDown", ctypes.c_int)
    ]


class MouseOpt():
    def __init__(self, email, password):
        super().__init__()
        ctypes.windll.user32.SetProcessDPIAware()
        print("鼠标加载成功！！！")
        try:  # 加载驱动
            # 获取当前绝对路径
            self.driver = ctypes.WinDLL(r'./mouse_dll.dll')
            # 声明函数原型
            self.listen_mouse = self.driver.listen_mouse
            self.listen_mouse.restype = MouseState
            email = email.encode('utf-8')  # example@qq.com为注册的email此处必须将后面必须指定email的编码为('utf-8')
            password = password.encode('utf-8')  # password是你注册时候的密码此处必须将后面必须指定email的编码为('utf-8')
            self.driver.mouse_open(email, password)  #控制鼠标

            # 定义截屏参数和返回类型
            self.driver.InitializeScreenshot.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
            self.driver.InitializeScreenshot.restype = None

            self.driver.ReleaseScreenshotResources.argtypes = []
            self.driver.ReleaseScreenshotResources.restype = None

            self.driver.CaptureScreen.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
            self.driver.CaptureScreen.restype = ctypes.POINTER(ctypes.c_ubyte)

            self.driver.FreeImageData.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
            self.driver.FreeImageData.restype = None

            # 初始化像素指针
            self.pixels_ptr = None
            # 初始化截图资源
            self.driver.InitializeScreenshot(email, password)

        except FileNotFoundError:
            print(f'错误, DLL 文件没有找到')

    def click(self, code):  # 点击鼠标左键
        self.driver.mouse_click(code)

    def move(self, x, y, oprt):  # 移动鼠标
        self.driver.mouse_move(x, y, 0, oprt)

    def press(self, oprt):
        self.driver.mouse_press(oprt)

    def listen_mouse(self):  # 获取鼠标的按键情况
        # 调用获取鼠标状态函数
        return self.listen_mouse

    def shotx(self, left, top, width, height, flagScreen):
        """
        截取屏幕区域并返回图像数据。
        :param left: 截取区域的左边界
        :param top: 截取区域的上边界
        :param width: 截取区域的宽度
        :param height: 截取区域的高度
        :param flagScreen: 屏幕模式（0 表示分辨率低于或等于 1920x1080, 1 表示分辨率高于或等于 2560x1440）
        """
        if width % 4 != 0:
            for i in range(1, 4):
                if (width - i) % 4 == 0:
                    left = round(left + (i / 2))
                    width -= i
                    break
        # 调用 DLL 截屏
        self.pixels_ptr = self.driver.CaptureScreen(left, top, width, height, flagScreen)
        # 转换为 NumPy 数组
        cpp_image = np.ctypeslib.as_array(self.pixels_ptr, shape=(height, width, 3))
        return cpp_image

    def destroy(self):
        # 释放图像数据
        if self.pixels_ptr:
            self.driver.FreeImageData(self.pixels_ptr)
            self.pixels_ptr = None
        # 释放截图资源
        # self.screenshot_dll.ReleaseScreenshotResources()

    def __enter__(self):
        """
        进入上下文时，返回类实例。
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        离开上下文时自动销毁资源。
        """
        self.destroy()
