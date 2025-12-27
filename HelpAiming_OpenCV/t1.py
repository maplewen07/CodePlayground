from MouseOpt import MouseOpt
import cv2

if __name__ == '__main__':
    email = "2931527112@qq.com"  # example@qq.com为注册的email
    password = "RZJX0819WRJ"  # password是你注册时候的密码
    drive = MouseOpt(email, password)
    drive.move(100, 100, 1)
    v = drive.listen_mouse()  # 获取鼠标的按键情况
    # 打印获取用户的的鼠标状态.
    print("Left button down:", v.leftButtonDown)  # 如果值为1表示当前鼠标左键正在被按下，0表示松开
    print("Right button down:", v.rightButtonDown)  # 如果值为1表示当前鼠标右正在被按下，0表示松开
    print("Middle button down:", v.middleButtonDown)  # 如果值为1表示当前鼠标中键正在被按下，0表示松开
    print("X1 button down:", v.x1ButtonDown)  # 如果值为1表示当前鼠标侧键1正在被按下，0表示松开
    print("X2 button down:", v.x2ButtonDown)  # 如果值为1表示当前鼠标侧键2正在被按下，0表示松开
    # image = drive.shotx(0, 0, 1919, 1080, 1)  # 截图操作
    # cv2.imshow("image", image)
    # cv2.waitKey(0)  # 等待按键
    # cv2.destroyAllWindows()  # 关闭窗口
