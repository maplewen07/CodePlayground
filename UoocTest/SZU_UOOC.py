import time
import threading
import logging
import requests

# @ Todo
# 一些说明：
# 这个脚本只适用于没有播放限制的课程。 需要该课程允许 同时观看不同视频。
# 原理： 在查看网页时，发现通过 https://www.uooc.net.cn/home/learn/markVideoLearn 提交视频进度。
# 怀疑只需要提交两次，一次表示视频开始观看，一次视频看完。
# 但是在实际过程中发现，在后端似乎有自动计时。
# 间隔20分钟后提交大部分都是成功的。

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
# 常量定义
CID = "XXXXXXX"  # 你的CID
COOKIE = (  # 按照你自己的COOKIE填
   "JSESSID=oet7dspoobhj3inlkdm794cgc1; Hm_lvt_d1a5821d95582e27154fc4a1624da9e3=1744812364; "
   "HMACCOUNT=241620BB546F856E; "
   "uooc_auth=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9"
   ".eyJyZW1lbWJlciI6dHJ1ZSwibG9naW5faG9zdCI6Ind3dy51b29jLm5ldC5jbiIsInN1YjEiOjAsInN1YiI6IjkzNDg3MiIsImV4cCI6MTc0NzQwNDM3N30.oFVzlG0zsQzmN-TTRUgrYHUggcq-xnw1_d2zqsblatk; account=15388366759; examRemindNum_1696839295=1; cerRemindNum_1696839295=1; tfstk=g4rjcNvLJIAbB3OunsBrddEfoAn_f5sEBdMTKRK2Bmnv6CeKaElq0s475WyKWoyZDdN_aWGY0mkqWfFEZxL9kAp-wxkwHECjDVK_BJiwblwMfAeTstcNnay0ncmOT6o1Y-2mX672ooGveLeopIpAzqhwDfiOT6SF4Zp-fs1Ugg88CgMiwxHtMVBS2AMjXIhY6b3-pAKxXcFOF4HmhKKxMxIJeAl-6cnT68BSIAUJNA7jB-6DUVrn0_o0Hbt9XoIilXiw7HtQVxgbX-hWhKZShqGKr2QQ0oFzBormr1Otj8zQ1PFG8UmbBrnxL-jXVDeYzlMzbO8sMSq7eu3WKH0zwoNsgD9OD8ijG2EquKK098wT84ZPpMmjDjUZmRJCg8Zbg-q7QdL-cmzSRoidxIhazJZsClfGVWw3q7M89G1A4GtEO6hk5LgHfYGFFTTMSW21zlnbJWv-kYDAYT6WNF0xEYhNFTTCuqHohW65FIE5.; formpath=/home/learn/index; formhash=/1696839295/15425456/497598887/1611432414/section; Hm_lpvt_d1a5821d95582e27154fc4a1624da9e3=1744812976"
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


def fetch_unit_learn(catalog_id, chapter_id, cid, section_id):
    """
    获取单元学习信息，并返回对应的资源ID。
    :param catalog_id: 目录ID
    :param chapter_id: 章节ID
    :param cid: 客户端ID
    :param section_id: 部分ID
    :return: 资源ID或空字符串
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
            return data['data'][0].get('id', "")
        else:
            logging.warning(f"未找到数据: catalog_id={catalog_id}, chapter_id={chapter_id}, section_id={section_id}")
            return ""
    except requests.exceptions.RequestException as e:
        logging.error(f"获取单元学习信息时发生错误: {e}")
        return None


def submit_info(chapter_id, cid, resource_id, section_id, pos=2000.0):
    """
    提交学习信息。

    :param pos: 视频播放位置
    :param chapter_id: 章节ID
    :param cid: 客户端ID
    :param resource_id: 资源ID
    :param section_id: 部分ID
    :return: None
    """
    headers = HEADERS.copy()
    if "formhash" in COOKIE:
        updated_cookie = COOKIE.split("formhash=")[0] + f"formhash=/{cid}/{chapter_id}/{resource_id}"
        headers["cookie"] = updated_cookie

    data = {
        "chapter_id": chapter_id,
        "cid": cid,
        "hidemsg_": True,
        "network": 2,
        "resource_id": resource_id,
        "section_id": section_id,
        "source": 1,
        "subsection_id": 0,
        "video_length": 2000.0,
        "video_pos": pos
    }

    try:
        response = requests.post(URL_MARK_VIDEO_LEARN, headers=headers, data=data)
        response.raise_for_status()
        result = response.json()
        logging.info(f"提交信息响应: {result}")
    except requests.exceptions.RequestException as e:
        logging.error(f"提交学习信息时发生错误: {e}")


def submit_info_periodically(chapter_id, cid, resource_id, section_id, interval=180, duration=1500):
    """
    每隔 `interval` 秒执行一次 SubmitInfo，持续 `duration` 秒。

    :param chapter_id: 章节ID
    :param cid: 客户端ID
    :param resource_id: 资源ID
    :param section_id: 部分ID
    :param interval: 执行间隔（秒），默认3分钟
    :param duration: 总持续时间（秒），默认25分钟
    """
    start_time = time.time()
    while (time.time() - start_time) < duration:
        submit_info(chapter_id, cid, resource_id, section_id, time.time() - start_time)
        time.sleep(interval)


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
    except requests.exceptions.RequestException as e:
        logging.error(f"获取章节列表时发生错误: {e}")
        return

    chapter_list = []

    for chapter in data.get("data", []):
        chapter_id = chapter.get("id")
        chapter_info = {
            "chapter_id": chapter_id,
            "SubUnits": []
        }

        children = chapter.get("children", [])
        for child in children:
            resource_id = fetch_unit_learn(
                catalog_id=child.get("id"),
                chapter_id=chapter_id,
                cid=CID,
                section_id=child.get("id")
            )
            if resource_id:
                chapter_info["SubUnits"].append({
                    "section_id": child.get("id"),
                    "resource_id": resource_id
                })
            else:
                logging.warning(f"未获取到 resource_id: chapter_id={chapter_id}, section_id={child.get('id')}")

        chapter_list.append(chapter_info)

    # 启动线程
    threads = []
    for chapter in chapter_list:
        chapter_id = chapter['chapter_id']
        for sub in chapter["SubUnits"]:
            section_id = sub['section_id']
            resource_id = sub['resource_id']
            thread = threading.Thread(
                target=submit_info_periodically,
                args=(chapter_id, CID, resource_id, section_id)
            )
            thread.start()
            threads.append(thread)
            logging.info(f"已启动线程: chapter_id={chapter_id}, section_id={section_id}")
            time.sleep(150)

    # 等待所有线程完成
    for thread in threads:
        thread.join()


if __name__ == "__main__":
    main()
