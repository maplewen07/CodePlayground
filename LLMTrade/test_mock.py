#!/usr/bin/env python3
"""
测试脚本：使用模拟客户端运行一次策略循环。
"""
import os
os.environ["USE_MOCK"] = "1"

from main import main

if __name__ == "__main__":
    # 主函数会进入无限循环，这里我们手动模拟一次迭代
    # 我们直接导入组件并手动调用一次 run_once
    from config import BotConfig
    from okx_client import MockOKXClient
    from llm_filter import LLMFilter
    from trend_bot import TrendBot
    
    cfg = BotConfig()
    client = MockOKXClient("dummy_key", "dummy_secret", "dummy_passphrase", cfg.base_url)
    llm = LLMFilter(cfg.enable_llm_filter)
    bot = TrendBot(cfg, client, llm)
    
    print("=== 开始模拟运行一次策略循环 ===")
    bot.run_once()
    print("=== 模拟运行完成 ===")
    print("状态已保存到 state.json")