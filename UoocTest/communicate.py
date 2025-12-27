import requests
import time

# 讨论用

url = "https://www.uooc.net.cn/Home/Threads/reply"
headers = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9",
    "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
    "origin": "https://www.uooc.net.cn",
    "priority": "u=1, i",
    "referer": "https://www.uooc.net.cn/home/course/xxxxxxxxxxx", # @Todo 记得找一下
    "sec-ch-ua": "\"Chromium\";v=\"135\", \"Not-A.Brand\";v=\"8\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "xsrf": ""  # The value for this header seems to be missing, you may need to add it
}

cookies = {
    
    # @Todo 直接把 cookie 复制过来就好    
}

data = {
    # @Todo 去网站找一下 https://www.uooc.net.cn/Home/Threads/reply 数据格式。
}

# 连续发送20次请求，每次间隔2分钟
for i in range(15):
    response = requests.post(url, headers=headers, cookies=cookies, data=data)
    print(f"第{i + 1}次请求响应: {response.status_code}")

    # 如果不是第一次请求，则等待2分钟
    if i < 19:  # 最后一次请求后不再等待
        print("等待2分钟...")
        time.sleep(120)  # 2分钟间隔 (120秒)
