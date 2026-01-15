import os
import json
import time
import hmac
import base64
import hashlib
import datetime as dt
from typing import Any, Dict, List, Optional

import requests


class OKXClient:
    def __init__(self, api_key: str, api_secret: str, passphrase: str, base_url: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    @staticmethod
    def _iso_timestamp_utc() -> str:
        # OKX/OKCoin 文档示例为毫秒 ISO8601：2020-12-08T09:08:57.715Z 
        now = dt.datetime.utcnow()
        return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(now.microsecond/1000):03d}Z"

    def _sign(self, timestamp: str, method: str, request_path: str, body: str) -> str:
        # sign = Base64(HMAC_SHA256(secret, timestamp + method + requestPath + body)) 
        prehash = f"{timestamp}{method.upper()}{request_path}{body}"
        mac = hmac.new(self.api_secret.encode("utf-8"), prehash.encode("utf-8"), hashlib.sha256)
        return base64.b64encode(mac.digest()).decode()

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None,
                 body: Optional[Dict[str, Any]] = None, auth: bool = False,
                 retry: int = 2) -> Dict[str, Any]:
        method = method.upper()
        params = params or {}
        body = body or {}

        # 组装 requestPath（GET 参数算在 requestPath，不算 body） 
        if method == "GET" and params:
            qs = "&".join([f"{k}={params[k]}" for k in params])
            request_path = f"{path}?{qs}"
        else:
            request_path = path

        body_str = "" if method == "GET" else json.dumps(body, separators=(",", ":"), ensure_ascii=False)

        headers = {}
        if auth:
            ts = self._iso_timestamp_utc()
            sign = self._sign(ts, method, request_path, body_str)
            headers.update({
                "OK-ACCESS-KEY": self.api_key,
                "OK-ACCESS-SIGN": sign,
                "OK-ACCESS-TIMESTAMP": ts,
                "OK-ACCESS-PASSPHRASE": self.passphrase,
            })

        url = self.base_url + request_path

        last_err = None
        for attempt in range(retry + 1):
            try:
                if method == "GET":
                    r = self.session.get(url, headers=headers, timeout=10)
                else:
                    r = self.session.post(self.base_url + path, headers=headers, data=body_str, timeout=10)

                data = r.json()
                # OKX/OKCoin 通常 code=="0" 表示成功
                if str(data.get("code")) == "0":
                    return data

                # 常见：接口偶发超时/压力（官方 FAQ 也建议错峰/重试） 
                last_err = RuntimeError(f"API error code={data.get('code')} msg={data.get('msg')} data={data.get('data')}")
            except Exception as e:
                last_err = e

            if attempt < retry:
                time.sleep(0.6 * (attempt + 1))

        raise last_err

    # ---------- 公共数据 ----------
    def get_server_time_ms(self) -> int:
        # GET /api/v5/public/time 
        data = self._request("GET", "/api/v5/public/time", auth=False)
        return int(data["data"][0]["ts"])

    def get_candles(self, inst_id: str, bar: str, limit: int) -> List[List[str]]:
        # GET /api/v5/market/candles 
        params = {"instId": inst_id, "bar": bar, "limit": str(limit)}
        data = self._request("GET", "/api/v5/market/candles", params=params, auth=False)
        # 返回：[[ts, o, h, l, c, vol, volCcy, ...], ...]，按“最近在前”
        return data["data"]

    def get_instruments_spot(self, inst_id: str) -> Dict[str, Any]:
        # GET /api/v5/public/instruments?instType=SPOT 
        params = {"instType": "SPOT", "instId": inst_id}
        data = self._request("GET", "/api/v5/public/instruments", params=params, auth=False)
        if not data["data"]:
            raise RuntimeError("Instrument not found, check instId.")
        return data["data"][0]

    # ---------- 私有数据 ----------
    def get_balance(self, ccy: str) -> Dict[str, Any]:
        # /api/v5/account/balance?ccy=BTC 等在文档签名示例中出现 
        params = {"ccy": ccy}
        return self._request("GET", "/api/v5/account/balance", params=params, auth=True)

    # ---------- 下单 ----------
    def place_order(self, inst_id: str, side: str, ord_type: str, sz: str,
                    px: Optional[str] = None, td_mode: str = "cash",
                    tgt_ccy: Optional[str] = None, cl_ord_id: Optional[str] = None) -> Dict[str, Any]:
        # POST /api/v5/trade/order 
        body = {
            "instId": inst_id,
            "tdMode": td_mode,
            "side": side,
            "ordType": ord_type,
            "sz": sz,
        }
        if px is not None:
            body["px"] = px
        if tgt_ccy is not None:
            body["tgtCcy"] = tgt_ccy
        if cl_ord_id is not None:
            body["clOrdId"] = cl_ord_id

        return self._request("POST", "/api/v5/trade/order", body=body, auth=True)

    def place_algo_order(self, body: Dict[str, Any]) -> Dict[str, Any]:
        # POST /api/v5/trade/order-algo 
        return self._request("POST", "/api/v5/trade/order-algo", body=body, auth=True)

    def cancel_advance_algos(self, items: List[Dict[str, str]]) -> Dict[str, Any]:
        # POST /api/v5/trade/cancel-advance-algos 
        return self._request("POST", "/api/v5/trade/cancel-advance-algos", body=items, auth=True)


class MockOKXClient(OKXClient):
    def __init__(self, api_key: str, api_secret: str, passphrase: str, base_url: str):
        super().__init__(api_key, api_secret, passphrase, base_url)
        self.mock_candles = self._generate_mock_candles()
        self.mock_balances = {
            "BTC": 0.5,
            "USDT": 5000.0,
        }
        self.mock_instrument = {
            "minSz": "0.0001",
            "lotSz": "0.00000001",
        }
        self.orders = []
        self.algos = []

    def _generate_mock_candles(self, count: int = 200) -> List[List[str]]:
        # 生成模拟的BTC/USDT小时K线数据，价格在 50000-60000 之间波动
        import random
        import time
        candles = []
        base_price = 55000.0
        now_ms = int(time.time() * 1000)
        for i in range(count):
            ts = now_ms - (count - i) * 3600 * 1000  # 每小时一个
            open_price = base_price + random.uniform(-500, 500)
            high = open_price + random.uniform(0, 300)
            low = open_price - random.uniform(0, 300)
            close = open_price + random.uniform(-200, 200)
            vol = random.uniform(1, 10)
            vol_ccy = vol * close
            candles.append([
                str(ts),
                f"{open_price:.2f}",
                f"{high:.2f}",
                f"{low:.2f}",
                f"{close:.2f}",
                f"{vol:.6f}",
                f"{vol_ccy:.2f}",
                "0"
            ])
        return candles

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None,
                 body: Optional[Dict[str, Any]] = None, auth: bool = False,
                 retry: int = 2) -> Dict[str, Any]:
        # 模拟请求，返回虚拟数据
        # 根据路径和方法返回不同的模拟响应
        if path == "/api/v5/public/time":
            import time
            ts = int(time.time() * 1000)
            return {"code": "0", "msg": "", "data": [{"ts": str(ts)}]}
        elif path == "/api/v5/market/candles":
            # 返回模拟K线数据
            return {"code": "0", "msg": "", "data": self.mock_candles}
        elif path == "/api/v5/public/instruments":
            return {"code": "0", "msg": "", "data": [self.mock_instrument]}
        elif path == "/api/v5/account/balance":
            ccy = params.get("ccy", "USDT") if params else "USDT"
            avail = self.mock_balances.get(ccy, 0.0)
            return {"code": "0", "msg": "", "data": [{
                "details": [{"ccy": ccy, "availBal": str(avail)}]
            }]}
        elif path == "/api/v5/trade/order":
            # 模拟下单成功
            order_id = f"mock_order_{len(self.orders)}"
            self.orders.append({"orderId": order_id, **body})
            return {"code": "0", "msg": "", "data": [{"ordId": order_id}]}
        elif path == "/api/v5/trade/order-algo":
            algo_id = f"mock_algo_{len(self.algos)}"
            self.algos.append({"algoId": algo_id, **body})
            return {"code": "0", "msg": "", "data": [{"algoId": algo_id}]}
        elif path == "/api/v5/trade/cancel-advance-algos":
            return {"code": "0", "msg": "", "data": []}
        else:
            # 默认返回成功
            return {"code": "0", "msg": "", "data": []}

    # 可以重写特定方法以提供更精确的模拟行为
    def get_candles(self, inst_id: str, bar: str, limit: int) -> List[List[str]]:
        # 直接返回模拟K线数据，忽略参数
        return self.mock_candles[-limit:]

    def get_instruments_spot(self, inst_id: str) -> Dict[str, Any]:
        return self.mock_instrument

    def get_balance(self, ccy: str) -> Dict[str, Any]:
        avail = self.mock_balances.get(ccy, 0.0)
        return {"code": "0", "msg": "", "data": [{
            "details": [{"ccy": ccy, "availBal": str(avail)}]
        }]}

    def place_order(self, inst_id: str, side: str, ord_type: str, sz: str,
                    px: Optional[str] = None, td_mode: str = "cash",
                    tgt_ccy: Optional[str] = None, cl_ord_id: Optional[str] = None) -> Dict[str, Any]:
        order_id = f"mock_order_{len(self.orders)}"
        self.orders.append({"orderId": order_id, "instId": inst_id, "side": side, "sz": sz})
        return {"code": "0", "msg": "", "data": [{"ordId": order_id}]}

    def place_algo_order(self, body: Dict[str, Any]) -> Dict[str, Any]:
        algo_id = f"mock_algo_{len(self.algos)}"
        self.algos.append({"algoId": algo_id, **body})
        return {"code": "0", "msg": "", "data": [{"algoId": algo_id}]}

    def cancel_advance_algos(self, items: List[Dict[str, str]]) -> Dict[str, Any]:
        return {"code": "0", "msg": "", "data": []}

    def get_server_time_ms(self) -> int:
        import time
        return int(time.time() * 1000)