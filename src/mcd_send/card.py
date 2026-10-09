"""给收件人生成一张「有人给你点了一份」的卡片。

这是整个项目里唯一面向**非程序员**的产物：下单的人看完方案就下单，
但收件人看到的只有外卖袋。这张卡片补上那一句话——谁点的、为什么点、
这顿吃了多少，一眼看完，顺手能转发。

零外部依赖、单文件 HTML、离线可开。图片和字体全部走系统字体和 CSS 图形，
不引用任何 CDN，保证在任何网络环境下都能正常显示。
"""

from __future__ import annotations

import html
from pathlib import Path

from .menu import Combo
from .planner import SendPlan


def _esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def _num(value: float | None, unit: str, digits: int = 0) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}{unit}"


def render_card(
    plan: SendPlan,
    combo: Combo,
    *,
    from_name: str = "",
    message: str = "",
    order_id: str = "",
) -> str:
    """渲染卡片 HTML。"""
    greeting = message or f"给你点了一份，趁热吃。"
    price = combo.price or {}
    payable = price.get("payable_yuan")
    total = price.get("total_yuan")
    saved = price.get("saved_yuan")

    items_html = "\n".join(
        f'<li><span class="n">{_esc(name)}</span></li>' for name in combo.names
    )

    metrics = [
        ("热量", _num(combo.energy_kcal, " kcal"), "按官方营养表加总"),
        ("钠", _num(combo.sodium_mg, " mg"), "单餐参考上限 1500mg"),
        ("蛋白质", _num(combo.protein_g, " g", 1), "按官方营养表加总"),
    ]
    metrics_html = "\n".join(
        f'<div class="m"><div class="mv">{value}</div>'
        f'<div class="mk">{_esc(label)}</div>'
        f'<div class="mh">{_esc(hint)}</div></div>'
        for label, value, hint in metrics
    )

    price_html = ""
    if payable is not None:
        parts = [f'<span class="pay">¥{payable:.2f}</span>']
        if total is not None and saved:
            parts.append(
                f'<span class="was">原价 ¥{total:.2f}</span>'
                f'<span class="save">省 ¥{saved:.2f}</span>'
            )
        price_html = f'<div class="priceline">{"".join(parts)}</div>'

    notes = ""
    if combo.notes:
        notes = (
            '<ul class="notes">'
            + "".join(f"<li>{_esc(n)}</li>" for n in combo.notes)
            + "</ul>"
        )

    order_line = f"订单号 {_esc(order_id)}" if order_id else ""
    distance = (
        f"距你约 {plan.store.distance_km:g}km"
        if plan.store.distance_km is not None
        else ""
    )
    eta = (
        f"预计送达约 {plan.store.eta_min:g} 分钟"
        if plan.store.eta_min is not None
        else ""
    )
    logistics = " · ".join(x for x in (distance, eta) if x)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>给你点了一份 · {_esc(plan.contact.alias)}</title>
<style>
  *{{box-sizing:border-box}}
  body{{
    margin:0;padding:32px 16px;
    background:#f4f2ed;color:#241f1a;
    font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
    display:flex;justify-content:center;
  }}
  .card{{
    width:100%;max-width:420px;background:#fffaf3;
    border:1px solid #e6ddcd;border-radius:20px;
    padding:30px 26px 24px;position:relative;
  }}
  .stamp{{
    position:absolute;top:22px;right:24px;
    width:52px;height:52px;border-radius:50%;
    border:2px solid #c0392b;color:#c0392b;
    display:flex;align-items:center;justify-content:center;
    font-size:11px;font-weight:600;line-height:1.15;text-align:center;
    transform:rotate(9deg);letter-spacing:.5px;
  }}
  .to{{font-size:13px;color:#9a8f7e;letter-spacing:1px;margin-bottom:6px}}
  .who{{font-size:24px;font-weight:600;margin:0 0 18px;letter-spacing:-.3px}}
  .msg{{
    font-size:15px;line-height:1.75;color:#3d352c;
    padding:16px 18px;background:#fff;border-radius:12px;
    border:1px solid #eee4d4;margin-bottom:20px;
  }}
  .msg .from{{display:block;margin-top:10px;font-size:13px;color:#9a8f7e;text-align:right}}
  h2{{
    font-size:12px;font-weight:600;color:#9a8f7e;letter-spacing:2px;
    margin:0 0 10px;text-transform:uppercase;
  }}
  ul.items{{list-style:none;margin:0 0 22px;padding:0}}
  ul.items li{{
    padding:10px 0;border-bottom:1px dashed #ece2d2;font-size:15px;
  }}
  ul.items li:last-child{{border-bottom:none}}
  ul.items .n{{font-weight:500}}
  .metrics{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:20px}}
  .m{{background:#fff;border:1px solid #eee4d4;border-radius:12px;padding:12px 10px;text-align:center}}
  .mv{{font-size:17px;font-weight:600;font-variant-numeric:tabular-nums;letter-spacing:-.3px}}
  .mk{{font-size:12px;color:#9a8f7e;margin-top:2px}}
  .mh{{font-size:10.5px;color:#bdb2a0;margin-top:5px;line-height:1.4}}
  .priceline{{display:flex;align-items:baseline;gap:10px;margin-bottom:16px;flex-wrap:wrap}}
  .pay{{font-size:26px;font-weight:600;font-variant-numeric:tabular-nums}}
  .was{{font-size:13px;color:#a89b88;text-decoration:line-through}}
  .save{{font-size:12px;color:#c0392b;background:#fbeceb;border-radius:20px;padding:2px 9px}}
  ul.notes{{margin:0 0 18px;padding-left:18px;font-size:12.5px;color:#8a7f6e;line-height:1.7}}
  .logi{{
    font-size:12.5px;color:#8a7f6e;border-top:1px solid #eee4d4;
    padding-top:14px;line-height:1.7;
  }}
  .logi .store{{color:#3d352c;font-weight:500}}
  .order{{font-size:11.5px;color:#bdb2a0;margin-top:6px;font-variant-numeric:tabular-nums}}
  .foot{{font-size:11px;color:#c4b9a8;margin-top:16px;line-height:1.6}}
</style>
</head>
<body>
<div class="card">
  <div class="stamp">有人<br>请客</div>
  <div class="to">TO</div>
  <div class="who">{_esc(plan.contact.alias)}</div>

  <div class="msg">
    {_esc(greeting)}
    <span class="from">—— {_esc(from_name or "一个惦记你的人")}</span>
  </div>

  <h2>这一份</h2>
  <ul class="items">
{items_html}
  </ul>

  <div class="metrics">
{metrics_html}
  </div>

  {price_html}
  {notes}

  <div class="logi">
    <div class="store">{_esc(plan.store.name)}</div>
    <div>{_esc(logistics)}</div>
    <div class="order">{order_line}</div>
  </div>

  <div class="foot">
    餐品信息与价格来自麦当劳中国官方 MCP 实时接口，营养数据按官方营养表逐项加总。
    本卡片由「麦麦代送 mcd-send-a-meal」生成，非麦当劳官方产品。
  </div>
</div>
</body>
</html>
"""


def write_card(html_text: str, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html_text, encoding="utf-8")
    return target
