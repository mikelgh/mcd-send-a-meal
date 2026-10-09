#!/usr/bin/env python3
"""麦麦代送 CLI。

用法示例：

    # 0. 先看平台当前真实提供了哪些 tool、各要什么参数
    python scripts/send_a_meal.py inspect

    # 1. 看地址簿里都有谁
    python scripts/send_a_meal.py contacts

    # 2. 出一份方案（只读，不会下单）。--dry-run 用离线样例数据，不需要 Token
    python scripts/send_a_meal.py plan --to 爸妈 --dry-run

    # 3. 确认无误再下单
    python scripts/send_a_meal.py send --to 爸妈 --combo 1 --confirm

    # 4. 查配送进度 / 生成给收件人的卡片
    python scripts/send_a_meal.py track --order-id XXX
    python scripts/send_a_meal.py card --to 爸妈 --out out/card.html --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcd_send import (  # noqa: E402
    Combo,
    McpError,
    execute_send,
    find_contact,
    known_relations,
    load_contacts,
    plan_send,
    rank_by_price,
    render_card,
    track_order,
    write_card,
)
from mcd_send.fixtures import FixtureTools  # noqa: E402


def say(message: str) -> None:
    print(message, file=sys.stderr)


def yuan(value) -> str:
    """PriceBreakdown 里存的已经是元，直接格式化即可。"""
    if value is None:
        return "—"
    return f"¥{value:.2f}"


def make_tools(dry_run: bool, city: str = "杭州"):
    if dry_run:
        say("[dry-run] 使用离线样例数据，不会访问麦当劳 MCP，也不会产生任何真实订单")
        return FixtureTools(city=city)
    from mcd_send.tools import McpTools

    return McpTools()


def _combo_line(index: int, combo: Combo) -> str:
    price = combo.price or {}
    tags = []
    if combo.energy_kcal is not None:
        tags.append(f"{combo.energy_kcal:g}kcal")
    if combo.sodium_mg is not None:
        tags.append(f"钠{combo.sodium_mg:g}mg")
    if combo.protein_g is not None:
        tags.append(f"蛋白{combo.protein_g:g}g")
    hit = f"  ★{'/'.join(combo.preference_hits)}" if combo.preference_hits else ""

    head = (
        f"  [{index}] {combo.label:<12} {' + '.join(combo.names)}\n"
        f"      应付 {yuan(price.get('payable_yuan'))}"
    )
    lines = [head]

    parts = []
    if price.get("total_yuan") is not None:
        parts.append(f"商品 ¥{price['total_yuan']:.2f}")
    if price.get("discount_yuan"):
        parts.append(f"券 −¥{price['discount_yuan']:.2f}")
    if price.get("delivery_yuan"):
        parts.append(f"配送 +¥{price['delivery_yuan']:.2f}")
    if parts:
        lines.append(f"         {'  '.join(parts)}")

    if price.get("coupon_name"):
        lines.append(f"         用了「{price['coupon_name']}」")
    lines.append(f"         {' · '.join(tags) or '营养数据缺失'}{hit}")
    return "\n".join(lines)


def cmd_contacts(args) -> int:
    contacts = load_contacts(args.contacts)
    if not contacts:
        say("地址簿是空的。")
        return 1
    print(f"共 {len(contacts)} 位收件人：\n")
    for contact in contacts:
        profile = contact.recipient_profile
        limits = []
        if profile.energy_max_kcal:
            limits.append(f"热量<={profile.energy_max_kcal:g}kcal")
        if profile.sodium_max_mg:
            limits.append(f"钠<={profile.sodium_max_mg:g}mg")
        if profile.protein_min_g:
            limits.append(f"蛋白>={profile.protein_min_g:g}g")
        if profile.no_ice:
            limits.append("去冰")
        if profile.avoid_keywords:
            limits.append("忌" + "/".join(profile.avoid_keywords))
        ready = "已绑定地址" if contact.address_id else "!! 缺 address_id"
        print(f"  {contact.alias:<8} {contact.city or '—':<6} {contact.relation:<10} "
              f"{ready}\n      约束：{'，'.join(limits) or '无'}")
        if profile.note:
            print(f"      备注：{profile.note}")
    print(f"\n可选关系类型：{'、'.join(known_relations())}")
    return 0


def cmd_inspect(args) -> int:
    tools = make_tools(args.dry_run)
    print(tools.inspect())
    if not args.dry_run:
        print("\n提示：把上面每个 tool 的真实参数名和本项目 tools.py 里写的对照一下，")
        print("不一致时不需要改代码——ToolSchemas.resolve() 会自动归一化匹配。")
    return 0


def cmd_plan(args) -> int:
    tools = make_tools(args.dry_run, city=args.city)
    try:
        plan = plan_send(
            tools,
            args.to,
            contacts_path=args.contacts,
            progress=say,
        )
    except (McpError, ValueError) as exc:
        say(f"\n出方案失败：{exc}")
        return 2

    if args.json:
        print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print()
    print("=" * 68)
    print(f"  代送方案 · 收件人 {plan.contact.alias}（{plan.contact.city or '未知城市'}）")
    print("=" * 68)
    print(f"  配送门店  {plan.store.name}（{plan.store.code}）")
    if plan.store.distance_km is not None:
        print(f"  距收件人  约 {plan.store.distance_km:g} km")
    if plan.store.eta_min is not None:
        print(f"  预计送达  约 {plan.store.eta_min:g} 分钟")
    print(f"  门店菜单  {plan.menu_size} 个在售餐品，其中 {plan.candidates_considered} 组进入核价")
    print(f"  可用券    {len(plan.coupons)} 张（已按收件人所在门店重查）")
    profile = plan.contact.recipient_profile
    if profile.note:
        print(f"  收件人约束 {profile.note}")
    print()

    ranked = rank_by_price(plan.combos)
    if not ranked:
        print("  没有可用的候选套餐。")
        return 1

    print("  候选方案（已按官方核价排序）：")
    for index, combo in enumerate(ranked, 1):
        print(_combo_line(index, combo))
        for note in combo.notes:
            print(f"      · {note}")
        print()

    if plan.warnings:
        print("  提醒：")
        for warning in plan.warnings:
            print(f"    - {warning}")
        print()

    best = ranked[0]
    print(f"  建议：[1] {best.label} —— {' + '.join(best.names)}")
    print()
    print("  下一步（复制即用）：")
    print(f"    python scripts/send_a_meal.py send --to {args.to} --combo 1 --confirm"
          + ("  --dry-run" if args.dry_run else ""))
    print()
    return 0


def cmd_send(args) -> int:
    tools = make_tools(args.dry_run, city=args.city)
    try:
        plan = plan_send(tools, args.to, contacts_path=args.contacts, progress=say)
    except (McpError, ValueError) as exc:
        say(f"\n出方案失败：{exc}")
        return 2

    ranked = rank_by_price(plan.combos)
    if not ranked:
        say("没有可下单的候选套餐。")
        return 1
    if not 1 <= args.combo <= len(ranked):
        say(f"--combo 超出范围，可选 1..{len(ranked)}")
        return 1

    chosen = ranked[args.combo - 1]
    price = chosen.price or {}
    print(f"\n即将下单：{' + '.join(chosen.names)}")
    print(f"  收件人  {plan.contact.alias}（{plan.contact.city or '未知城市'}）")
    print(f"  门店    {plan.store.name}")
    print(f"  实付    {yuan(price.get('payable_yuan'))}"
          f"  （原价 {yuan(price.get('total_yuan'))}）")

    if not args.confirm:
        print("\n以上是预演。确认无误后，在命令末尾加 --confirm 再执行一次。")
        return 0

    try:
        result = execute_send(tools, plan, combo=chosen, confirm=True, progress=say)
    except (McpError, ValueError, PermissionError) as exc:
        say(f"\n下单失败：{exc}")
        return 2

    print(f"\n订单已创建：{result.order_id}")
    if result.pay_url:
        print(f"支付链接：{result.pay_url}")
    if result.status:
        print(f"当前状态：{result.status}")
    print(f"\n查询进度：python scripts/send_a_meal.py track --order-id {result.order_id}")
    if args.card:
        html_text = render_card(
            plan,
            chosen,
            from_name=args.from_name,
            message=args.message,
            order_id=result.order_id,
        )
        path = write_card(html_text, args.card)
        print(f"收件人卡片已生成：{path}")
    return 0


def cmd_track(args) -> int:
    tools = make_tools(args.dry_run, city=args.city)
    try:
        info = track_order(tools, args.order_id)
    except (McpError, ValueError) as exc:
        say(f"查询失败：{exc}")
        return 2
    print(f"订单 {info['order_id']}")
    print(f"  状态      {info.get('status') or '—'}")
    print(f"  预计送达  {info.get('eta_min') or '—'}")
    print(f"  收件人    {info.get('receiver') or '—'}")
    print(f"  地址      {info.get('address') or '—'}")
    return 0


def cmd_card(args) -> int:
    tools = make_tools(args.dry_run, city=args.city)
    try:
        plan = plan_send(tools, args.to, contacts_path=args.contacts, progress=say)
    except (McpError, ValueError) as exc:
        say(f"\n出方案失败：{exc}")
        return 2
    ranked = rank_by_price(plan.combos)
    if not ranked:
        say("没有可用的候选套餐。")
        return 1
    chosen = ranked[min(max(args.combo, 1), len(ranked)) - 1]
    html_text = render_card(
        plan, chosen, from_name=args.from_name, message=args.message
    )
    path = write_card(html_text, args.out)
    print(f"卡片已生成：{path.resolve()}")
    return 0


def cmd_address_new(args) -> int:
    tools = make_tools(args.dry_run, city=args.city)
    try:
        result = tools.create_address(args.name, args.phone, args.address, args.city, args.address_detail)
    except McpError as exc:
        say(f"创建地址失败：{exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\n把上面的 addressId 填进地址簿对应联系人的 address_id 字段即可。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="send_a_meal",
        description="麦麦代送 —— 用麦当劳 MCP 给「别人」点一份",
    )
    parser.add_argument("--contacts", help="地址簿文件路径", default=None)
    parser.add_argument("--dry-run", action="store_true", help="离线样例数据，不需要 Token")
    parser.add_argument("--city", default="杭州", help="离线模式的收件人城市")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("contacts", help="列出地址簿").set_defaults(func=cmd_contacts)

    p_inspect = sub.add_parser("inspect", help="打印 MCP Server 的真实工具与参数")
    p_inspect.set_defaults(func=cmd_inspect)

    p_plan = sub.add_parser("plan", help="出一份代送方案（只读）")
    p_plan.add_argument("--to", required=True, help="收件人称呼，如 爸妈")
    p_plan.add_argument("--json", action="store_true", help="输出 JSON")
    p_plan.set_defaults(func=cmd_plan)

    p_send = sub.add_parser("send", help="按方案下单")
    p_send.add_argument("--to", required=True)
    p_send.add_argument("--combo", type=int, default=1, help="选第几组方案，默认 1")
    p_send.add_argument("--confirm", action="store_true", help="确认下单（不加则只预演）")
    p_send.add_argument("--from-name", default="", help="卡片上的落款")
    p_send.add_argument("--message", default="", help="卡片上的一句话")
    p_send.add_argument("--card", default="", help="下单后顺便生成卡片到该路径")
    p_send.set_defaults(func=cmd_send)

    p_track = sub.add_parser("track", help="查配送进度")
    p_track.add_argument("--order-id", required=True)
    p_track.set_defaults(func=cmd_track)

    p_card = sub.add_parser("card", help="只生成收件人卡片，不下单")
    p_card.add_argument("--to", required=True)
    p_card.add_argument("--combo", type=int, default=1)
    p_card.add_argument("--from-name", default="")
    p_card.add_argument("--message", default="")
    p_card.add_argument("--out", default="out/card.html")
    p_card.set_defaults(func=cmd_card)

    p_addr = sub.add_parser("address-new", help="为收件人新建一条配送地址")
    p_addr.add_argument("--name", required=True, help="收件人姓名")
    p_addr.add_argument("--phone", required=True, help="收件人手机号")
    p_addr.add_argument("--address", required=True, help="街道/门牌等地址主体")
    p_addr.add_argument("--city", required=True, help="城市（必填，真实接口要求）")
    p_addr.add_argument("--address-detail", default=None, help="地址详情（省略则与 --address 相同）")
    p_addr.set_defaults(func=cmd_address_new)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        say("\n已中断。")
        return 130
    except McpError as exc:
        say(f"\nMCP 调用失败：{exc}")
        return 2
    except (ValueError, PermissionError, OSError) as exc:
        say(f"\n{exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
