import win32api
import win32con
import pyWinhook as pyHook
import pythoncom
import threading
import time

# 全局控制变量
detection_enabled = True
running = True


def mouse_handler(event):
    """专用游戏鼠标事件处理器"""
    global detection_enabled

    print(event.MessageName)
    # 检测侧键按下（通常XButton1是侧键1，XButton2是侧键2）
    if event.MessageName == 'mouse middle down':
        detection_enabled = not detection_enabled
        status = "启用" if detection_enabled else "禁用"
        print(f"[游戏模式] 检测状态已切换：{status}")

    # 必须返回True保持事件传递
    return True


def hook_thread():
    """专用钩子线程"""
    hm = pyHook.HookManager()
    hm.MouseAll = mouse_handler
    hm.HookMouse()

    # 保持消息循环
    while running:
        pythoncom.PumpWaitingMessages()
        time.sleep(0.01)


if __name__ == "__main__":
    print("游戏输入监听器已启动")
    print("侧键1切换检测状态")
    print("按Ctrl+C安全退出")

    # 启动钩子线程
    hook_thread = threading.Thread(target=hook_thread)
    hook_thread.daemon = True
    hook_thread.start()

    try:
        while running:
            time.sleep(1)
    except KeyboardInterrupt:
        running = False
        hook_thread.join()
        print("已安全退出")
