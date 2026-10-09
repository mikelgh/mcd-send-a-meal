"""离线演示后端。

存在的意义：让整个 Skill **在没有 Token 的机器上也能跑通**，
评委、同事、甚至你在地铁上都能 `--dry-run` 看完整流程。

这里的数据是为了演示结构而编的样例，不是真实报价。
做任何真实决策请连真正的 MCP Server。
"""

from __future__ import annotations

from typing import Any

MEALS: list[dict[str, Any]] = [
    {"mealCode": "M001", "name": "巨无霸汉堡", "categoryName": "汉堡"},
    {"mealCode": "M002", "name": "麦辣鸡腿汉堡", "categoryName": "汉堡"},
    {"mealCode": "M003", "name": "双层吉士汉堡", "categoryName": "汉堡"},
    {"mealCode": "M004", "name": "板烧鸡腿堡", "categoryName": "汉堡"},
    {"mealCode": "S001", "name": "麦乐鸡 5 块", "categoryName": "小食"},
    {"mealCode": "S002", "name": "中薯条", "categoryName": "小食"},
    {"mealCode": "S003", "name": "大薯条", "categoryName": "小食"},
    {"mealCode": "S004", "name": "玉米杯", "categoryName": "小食"},
    {"mealCode": "D001", "name": "中杯可乐", "categoryName": "饮品"},
    {"mealCode": "D002", "name": "大杯可乐", "categoryName": "饮品"},
    {"mealCode": "D003", "name": "鲜煮咖啡", "categoryName": "饮品"},
    {"mealCode": "D004", "name": "优品豆浆", "categoryName": "饮品"},
    {"mealCode": "D005", "name": "冰牛奶", "categoryName": "饮品"},
    {"mealCode": "T001", "name": "麦旋风", "categoryName": "甜品"},
    {"mealCode": "T002", "name": "圆筒冰淇淋", "categoryName": "甜品"},
]

NUTRITION: list[dict[str, Any]] = [
    {"name": "巨无霸汉堡", "energy": 550, "sodium": 950, "protein": 26, "fat": 30},
    {"name": "麦辣鸡腿汉堡", "energy": 570, "sodium": 1050, "protein": 24, "fat": 32},
    {"name": "双层吉士汉堡", "energy": 450, "sodium": 1050, "protein": 25, "fat": 23},
    {"name": "板烧鸡腿堡", "energy": 430, "sodium": 900, "protein": 25, "fat": 17},
    {"name": "麦乐鸡 5 块", "energy": 230, "sodium": 480, "protein": 14, "fat": 13},
    {"name": "中薯条", "energy": 340, "sodium": 210, "protein": 4, "fat": 16},
    {"name": "大薯条", "energy": 460, "sodium": 290, "protein": 6, "fat": 22},
    {"name": "玉米杯", "energy": 90, "sodium": 5, "protein": 3, "fat": 1},
    {"name": "中杯可乐", "energy": 150, "sodium": 15, "protein": 0, "fat": 0},
    {"name": "大杯可乐", "energy": 220, "sodium": 20, "protein": 0, "fat": 0},
    {"name": "鲜煮咖啡", "energy": 5, "sodium": 5, "protein": 0, "fat": 0},
    {"name": "优品豆浆", "energy": 150, "sodium": 20, "protein": 8, "fat": 4},
    {"name": "冰牛奶", "energy": 130, "sodium": 100, "protein": 7, "fat": 5},
    {"name": "麦旋风", "energy": 300, "sodium": 150, "protein": 6, "fat": 10},
    {"name": "圆筒冰淇淋", "energy": 150, "sodium": 60, "protein": 4, "fat": 5},
    # 故意留一项不在菜单里的，用来演示「营养表未收录」路径
    {"name": "季节限定麦炫酷", "energy": 260, "sodium": 90, "protein": 3, "fat": 8},
]

# 单位：分（和平台保持一致，演示「分/元」这个坑）
UNIT_PRICE: dict[str, int] = {
    "M001": 2350, "M002": 2200, "M003": 1900, "M004": 2150,
    "S001": 1250, "S002": 1150, "S003": 1350, "S004": 1050,
    "D001": 900, "D002": 1050, "D003": 1050, "D004": 1200, "D005": 1100,
    "T001": 1350, "T002": 550,
}

COUPONS: list[dict[str, Any]] = [
    {"couponId": "C-30-15", "name": "满 30 减 15", "discountAmount": 1500,
     "expireTime": "2026-10-20 23:59:59", "minAmount": 3000},
    {"couponId": "C-45-20", "name": "满 45 减 20", "discountAmount": 2000,
     "expireTime": "2026-10-18 23:59:59", "minAmount": 4500},
    {"couponId": "C-20-8", "name": "满 20 减 8", "discountAmount": 800,
     "expireTime": "2026-10-25 23:59:59", "minAmount": 2000},
]

DELIVERY_FEE = 900


class FixtureTools:
    """和 McpTools 同接口的离线实现。"""

    def __init__(self, city: str = "杭州") -> None:
        self.city = city
        self.calls: list[tuple[str, dict]] = []

    def _log(self, name: str, args: dict) -> None:
        self.calls.append((name, args))

    def now(self) -> dict:
        self._log("now-time-info", {})
        return {"datetime": "2026-10-09 19:45:00", "weekday": "周五"}

    def list_addresses(self) -> list[dict]:
        self._log("delivery-query-addresses", {})
        return [
            {"addressId": "A-HZ-01", "city": "杭州", "detail": "** 小区 ** 幢 ** 室"},
            {"addressId": "A-SZ-02", "city": "深圳", "detail": "** 大厦 ** 层"},
        ]

    def create_address(self, contact_name: str, phone: str, address: str, city: str = "", address_detail: str | None = None) -> dict:
        self._log("delivery-create-address", {"contactName": contact_name})
        return {"addressId": "A-NEW-99", "city": city or self.city}

    def stores_for_address(self, address_id: str, be_type: str = "5") -> list[dict]:
        self._log("delivery-query-stores", {"addressId": address_id})
        return [
            {"storeCode": "HZ-0188", "storeName": "杭州文三路店", "beCode": "B-HZ-0188",
             "distance": 1.2, "eta": 26, "businessStatus": "营业中", "beType": 5},
            {"storeCode": "HZ-0231", "storeName": "杭州黄龙店", "beCode": "B-HZ-0231",
             "distance": 2.7, "eta": 34, "businessStatus": "营业中", "beType": 5},
            {"storeCode": "HZ-0402", "storeName": "杭州西溪店", "beCode": "B-HZ-0402",
             "distance": 4.9, "eta": 48, "businessStatus": "休息中", "beType": 5},
        ]

    def nearby_stores(self, keyword: str, be_type: str = "5", search_type: str = "1") -> list[dict]:
        self._log("query-nearby-stores", {"keyword": keyword})
        return self.stores_for_address("A-LOCAL")

    def meals(self, store_code: str, be_code: str = "", be_type: str = "") -> list[dict]:
        self._log("query-meals", {"storeCode": store_code, "beCode": be_code, "beType": be_type})
        return list(MEALS)

    def meal_detail(self, store_code: str, meal_code: str, be_code: str = "", be_type: str = "") -> dict:
        self._log("query-meal-detail", {"storeCode": store_code, "mealCode": meal_code})
        for meal in MEALS:
            if meal["mealCode"] == meal_code:
                return {**meal, "canReplace": ["去冰", "少酱", "去酸瓜"], "spuId": meal_code}
        return {}

    def nutrition(self) -> list[dict]:
        self._log("list-nutrition-foods", {})
        return list(NUTRITION)

    def store_coupons(self, store_code: str, be_code: str = "", be_type: str = "") -> list[dict]:
        self._log("query-store-coupons", {"storeCode": store_code})
        return list(COUPONS)

    def claimable_coupons(self) -> list[dict]:
        self._log("available-coupons", {})
        return list(COUPONS)

    def auto_bind_coupons(self) -> dict:
        self._log("auto-bind-coupons", {})
        return {"bound": len(COUPONS), "message": "（离线演示，未真实领券）"}

    def my_coupons(self) -> list[dict]:
        self._log("query-my-coupons", {})
        return list(COUPONS)

    def calculate_price(self, payload: dict) -> dict:
        self._log("calculate-price", payload)
        items = payload.get("items") or []
        subtotal = 0
        for item in items:
            code = str(item.get("mealCode") or "")
            subtotal += UNIT_PRICE.get(code, 0) * int(item.get("count") or 1)

        discount = 0
        coupon_id = payload.get("couponId")
        if coupon_id:
            for coupon in COUPONS:
                if coupon["couponId"] == coupon_id and subtotal >= coupon["minAmount"]:
                    discount = coupon["discountAmount"]
                    break

        delivery = DELIVERY_FEE if int(payload.get("orderType") or 1) == 1 else 0
        payable = max(subtotal - discount + delivery, 0)
        return {
            "totalAmount": subtotal,
            "deliveryFee": delivery,
            "discountAmount": discount,
            "payableAmount": payable,
        }

    def create_order(self, payload: dict) -> dict:
        self._log("create-order", payload)
        return {
            "orderId": "DEMO-20261009-0001",
            "payUrl": "https://example.invalid/demo-pay",
            "status": "待支付",
            "message": "（离线演示，未产生真实订单）",
        }

    def query_order(self, order_id: str) -> dict:
        self._log("query-order", {"orderId": order_id})
        return {
            "orderId": order_id,
            "status": "配送中",
            "estimateTime": 18,
            "receiverName": "（演示收件人）",
            "address": f"{self.city} ** 小区 ** 幢",
        }

    def cancel_order(self, order_id: str, reason: str = "") -> dict:
        self._log("cancel-order", {"orderId": order_id, "cancelReason": reason})
        return {"orderId": order_id, "status": "已取消"}

    def inspect(self) -> str:
        return "（离线演示模式，没有连接真实 MCP Server）"
