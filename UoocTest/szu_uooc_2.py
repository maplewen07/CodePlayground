import time
import threading
import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# @Todo
# 在之前版本上优化了数据解析。

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# 常量定义
CID = "xxxxx"  # 你的CID
COOKIE = (  # 按照你自己的COOKIE填
    "account=15388366759; examRemindNum_1696839295=1; cerRemindNum_1696839295=1; JSESSID=lji9dfj7o629l2gidvsu17hlp5; "
    "uooc_auth=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9"
    ".eyJyZW1lbWJlciI6dHJ1ZSwibG9naW5faG9zdCI6Ind3dy51b29jLm5ldC5jbiIsInN1YjEiOjAsInN1YiI6IjkzNDg3MiIsImV4cCI6MTc4MTI1NDIyMH0.g1VQ67IoXV5fBPCTdTfMmwrR5C-KfJ7OY4f6rHbCGC8; Hm_lvt_d1a5821d95582e27154fc4a1624da9e3=1765653609,1765702219; HMACCOUNT=F212755D50502D7E; tfstk=gvkxXCfBvUYD_b7VDVAkSnbPtEKuMQmVyqoCIP4c143-AD701o2mWPU-rjXifElty2mX0S2bGuZ7xoEf1ON_Nik-JOXDuIo1BR26-evHKmo0QRThUMGY2irgft_1So15PRqtBtnM8mo4QgSl5BcS0dEJAn4_CVw7NkqbCla_G3p7Yz6bftw_P3EaPRZ_1O97FkqOhlg_C3n7zlw_5VNX20azfRasQ5-YziZABjcO9Tr2de5O6YEYMPBgrOHKk9c7R4z5CeNgDAaIczB1IynQoqi-mEBEq-ojJk0DFt3KYYu8V299yRur1VZtPp7g3X0qL7nyOTiYHzVQumO197PTkbMbwG6s484TTf3vkszji4FUV7s9Lu03Pmkjwh7Sc24YhuNkdHn71bD4TxY5HJGEm-cs7BfzHcGbeg7iKvImPw4LjstJ215aGu8p-ll2LwrR4uUHcS1N_5qPIsH1p15asPE8-nER_1PyX; formpath=/home/learn/index; Hm_lpvt_d1a5821d95582e27154fc4a1624da9e3=1765721934; formhash=/292451367/1696044314/322225920/704093766/section"
)
URL_LIST = f"https://www.uooc.net.cn/home/learn/getCatalogList?cid={CID}&hidemsg_=true&show="
URL_GET_UNIT_LEARN = "https://www.uooc.net.cn/home/learn/getUnitLearn"
URL_MARK_VIDEO_LEARN = "https://www.uooc.net.cn/home/learn/markVideoLearn"

# 统一请求头
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "zh-CN,zh;q=0.9",
    "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
    "cookie": COOKIE,
    "origin": "https://www.uooc.net.cn",
    "priority": "u=1, i",
    "referer": "https://www.uooc.net.cn/home/learn/index",
    "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "xsrf": ""
}


def extract_video_info(data):
    """
    提取视频的最小标题和相关信息
    """
    video_info_list = []
    for chapter in data.get("data", []):
        chapter_id = chapter.get("id")
        for child in chapter.get("children", []):
            section_id = child.get("id")

            for resource_data in child.get("icon_list"):
                resource_id = resource_data.get("id")

                video_info_list.append({
                    "chapter_id": chapter_id,
                    "section_id": section_id,
                    "sub_section_id": 0,
                    'resource_id': resource_id
                })

            for sub_section in child.get("children", []):
                sub_section_id = sub_section.get("id")

                for resource_data in sub_section.get("icon_list"):
                    resource_id = resource_data.get("id")

                    video_info_list.append({
                        "chapter_id": chapter_id,
                        "section_id": section_id,
                        "sub_section_id": sub_section_id,
                        'resource_id': resource_id
                    })
    return video_info_list


def fetch_unit_learn(catalog_id, chapter_id, cid, section_id):
    """
    获取单元学习信息，并返回对应的资源ID。
    """
    params = {
        "catalog_id": catalog_id,
        "chapter_id": chapter_id,
        "cid": cid,
        "hidemsg_": "true",
        "section_id": section_id,
        "show": ""
    }
    try:
        response = requests.get(URL_GET_UNIT_LEARN, headers=HEADERS, params=params)
        response.raise_for_status()
        data = response.json()
        if "data" in data and data['data']:
            return data['data'][0]
        else:
            logging.warning(f"未找到数据: catalog_id={catalog_id}, chapter_id={chapter_id}, section_id={section_id}")
            return ""
    except requests.exceptions.RequestException as e:
        logging.error(f"获取单元学习信息时发生错误: {e}")
        return None


def submit_info(chapter_id, cid, resource_id, section_id, sub_section_id, pos=2000.0):
    """
    提交学习信息。 

    :param pos: 视频播放位置
    :param chapter_id: 章节ID
    :param cid: 客户端ID
    :param resource_id: 资源ID
    :param section_id: 部分ID
    """
    headers = HEADERS.copy()
    if "formhash" in COOKIE:
        updated_cookie = COOKIE.split("formhash=")[0] + f"formhash=/{cid}/{chapter_id}/{section_id}/{sub_section_id}"
        headers["cookie"] = updated_cookie

    data = {
        "chapter_id": chapter_id,
        "cid": cid,
        "hidemsg_": True,
        "network": 2,
        "resource_id": resource_id,
        "section_id": section_id,
        "source": 1,
        "subsection_id": sub_section_id,
        "video_length": 2000.0,
        "video_pos": pos
    }

    try:
        response = requests.post(URL_MARK_VIDEO_LEARN, headers=headers, data=data)
        response.raise_for_status()
        result = response.json()
        if result.get('code') == 600:
            logging.info(
                f"视频资源类型错误: chapter_id={chapter_id}, section_id={section_id}, sub_section_id={sub_section_id}")
        logging.info(f"提交信息: {result}")
        return result
    except requests.exceptions.RequestException as e:
        logging.error(f"提交学习信息时发生错误: {e}")
        return None


def submit_info_periodically(chapter_id, cid, resource_id, section_id, sub_section_id, stop_event):
    """
    每隔 `interval` 秒执行一次 SubmitInfo，持续 `duration` 秒。
    """
    start_time = time.time()
    tmp = 0
    while not stop_event.is_set():  # 判断线程是否应该停止
        tmp = time.time() - start_time
        result = submit_info(chapter_id, cid, resource_id, section_id, sub_section_id, 2000)
        if result:
            if result.get('data', {}).get('finished') == 1:
                logging.info(f"视频 {section_id} 已经观看完成，不再继续提交信息")
                stop_event.set()  # 设置停止事件，停止该线程
            elif result.get('msg') == '视频资源类型错误':
                logging.info(
                    f"视频资源类型错误，停止线程: chapter_id={chapter_id}, section_id={section_id}, sub_section_id={sub_section_id}")
                stop_event.set()  # 设置停止事件，停止该线程
        time.sleep(1)


def main():
    """
    主函数，负责获取章节列表并启动相应的线程执行提交任务。
    """
    data = {
        "cid": CID,
        "hidemsg_": "true",
        "show": ""
    }
    try:
        response = requests.post(URL_LIST, headers=HEADERS, data=data)
        response.raise_for_status()
        data = response.json()
        logging.info("成功获取章节列表")
    except requests.exceptions.RequestException as e:
        logging.error(f"获取章节列表时发生错误: {e}")
        return

    video_info_list = extract_video_info(data)

    # 使用ThreadPoolExecutor控制最大线程数为20
    with ThreadPoolExecutor(max_workers=10) as executor:
        stop_events = []
        futures = []

        for video_info in video_info_list:
            chapter_id = video_info.get("chapter_id")
            section_id = video_info.get("section_id")
            sub_section_id = video_info.get("sub_section_id")
            resource_id = video_info.get("resource_id")

            stop_event = threading.Event()
            stop_events.append(stop_event)

            # 提交任务到线程池
            future = executor.submit(submit_info_periodically, chapter_id, CID, resource_id, section_id, sub_section_id, stop_event)
            futures.append(future)
            logging.info(f"启动线程: chapter_id={chapter_id}, section_id={section_id}")

        # 等待所有线程完成
        for future in as_completed(futures):
            future.result()

    logging.info("所有任务已完成，程序结束")


if __name__ == "__main__":
    main()
