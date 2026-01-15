import os
import time
import datetime as dt

from config import BotConfig
from okx_client import OKXClient, MockOKXClient
from llm_filter import LLMFilter
from trend_bot import TrendBot


def sleep_to_next_hour():
    now = dt.datetime.now()
    nxt = (now.replace(minute=0, second=5, microsecond=0) + dt.timedelta(hours=1))
    sec = (nxt - now).total_seconds()
    if sec > 0:
        time.sleep(sec)


def main():
    cfg = BotConfig()

    api_key = os.getenv("OKX_API_KEY", "").strip()
    api_secret = os.getenv("OKX_API_SECRET", "").strip()
    passphrase = os.getenv("OKX_API_PASSPHRASE", "").strip()
    use_mock = os.getenv("USE_MOCK", "").lower() in ("1", "true", "yes")

    # 如果启用模拟模式或缺少API密钥，则使用模拟客户端
    if use_mock or not (api_key and api_secret and passphrase):
        if use_mock:
            print("[INFO] 使用模拟客户端 (USE_MOCK enabled)")
        else:
            print("[WARN] 缺少API密钥，自动切换到模拟客户端模式")
            # 设置虚拟值，避免后续检查错误
            api_key = api_key or "dummy_key"
            api_secret = api_secret or "dummy_secret"
            passphrase = passphrase or "dummy_passphrase"
        client = MockOKXClient(api_key, api_secret, passphrase, cfg.base_url)
    else:
        client = OKXClient(api_key, api_secret, passphrase, cfg.base_url)

    llm = LLMFilter(cfg.enable_llm_filter)
    bot = TrendBot(cfg, client, llm)

    print("Bot started. Running on hourly cadence.")
    while True:
        try:
            bot.run_once()
        except Exception as e:
            print(f"[ERROR] {e}")
        sleep_to_next_hour()


if __name__ == "__main__":
    main()