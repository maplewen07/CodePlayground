from typing import Any, Dict


class LLMFilter:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def allow_trade(self, payload: Dict[str, Any]) -> bool:
        """
        这里是“接口位”：你把 payload 发给大模型，大模型返回 JSON：
          {"allow": true/false, "reason": "..."}
        模板里默认永远允许（enabled=False 或未接入）
        """
        if not self.enabled:
            return True

        # TODO: 在这里接入你的大模型 API
        # 示例：return result_json.get("allow", False)
        return True