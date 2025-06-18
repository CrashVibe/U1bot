#!/usr/bin/env python3
"""
货币数据可视化分析工具
读取 coin_analysis_*.json 文件并生成可视化报告
"""

import glob
import json
import os


def find_latest_analysis_file():
    """查找最新的分析文件"""
    pattern = "coin_analysis_*.json"
    files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=os.path.getctime)


def generate_text_chart(data, title, width=50):
    """生成简单的文本图表"""
    print(f"\n📊 {title}")
    print("=" * (len(title) + 4))

    max_value = max(data.values()) if data else 1

    for label, value in data.items():
        bar_length = int((value / max_value) * width)
        bar = "█" * bar_length
        percentage = (value / sum(data.values())) * 100 if sum(data.values()) > 0 else 0
        print(f"{label:<20} {bar:<{width}} {value:>4} ({percentage:5.1f}%)")


def analyze_user_segments(user_details):
    """分析用户细分"""
    segments = {
        "新手 (≤50金币)": [],
        "进阶 (51-200金币)": [],
        "中级 (201-1000金币)": [],
        "高级 (1001-5000金币)": [],
        "专家 (5001-10000金币)": [],
        "大佬 (>10000金币)": [],
    }

    for user in user_details:
        coin = user["current_coin"]
        if coin <= 50:
            segments["新手 (≤50金币)"].append(user)
        elif coin <= 200:
            segments["进阶 (51-200金币)"].append(user)
        elif coin <= 1000:
            segments["中级 (201-1000金币)"].append(user)
        elif coin <= 5000:
            segments["高级 (1001-5000金币)"].append(user)
        elif coin <= 10000:
            segments["专家 (5001-10000金币)"].append(user)
        else:
            segments["大佬 (>10000金币)"].append(user)

    return {k: len(v) for k, v in segments.items()}


def calculate_consumption_potential(user_details):
    """计算消费潜力"""
    total_coins = sum(user["current_coin"] for user in user_details)

    # 按不同价格点计算能买得起的用户数
    price_points = [10, 50, 100, 200, 500, 1000, 2000, 5000]
    affordability = {}

    for price in price_points:
        affordable_users = len([u for u in user_details if u["current_coin"] >= price])
        affordability[f"{price}金币"] = affordable_users

    return affordability, total_coins


def generate_pricing_recommendations(summary):
    """生成详细的定价建议"""
    wealth_dist = summary["wealth_distribution"]
    total_users = summary["total_users"]

    print("\n💰 详细定价策略分析")
    print("=" * 30)

    # 分析不同价格区间的用户覆盖
    low_income = wealth_dist["低收入 (1-100金币)"] + wealth_dist["贫困 (0金币)"]
    mid_income = wealth_dist["中等收入 (101-500金币)"]
    high_income = wealth_dist["高收入 (501-1000金币)"]
    wealthy = wealth_dist["富裕 (1000+金币)"]

    print("\n🎯 目标用户群体分析:")
    print(
        f"  大众市场 (0-500金币): {low_income + mid_income}人 ({(low_income + mid_income) / total_users * 100:.1f}%)"
    )
    print(
        f"  高端市场 (500+金币): {high_income + wealthy}人 ({(high_income + wealthy) / total_users * 100:.1f}%)"
    )
    print(f"  奢侈品市场 (1000+金币): {wealthy}人 ({wealthy / total_users * 100:.1f}%)")

    prices = summary["recommended_prices"]
    print("\n💎 推荐商品定价矩阵:")
    print(
        f"  日常消费品: {prices['促销价格']}-{prices['低价商品 (面向所有用户)']} 金币"
    )
    print(
        f"  标准商品: {prices['低价商品 (面向所有用户)']}-{prices['中价商品 (面向中等收入)']} 金币"
    )
    print(
        f"  高端商品: {prices['中价商品 (面向中等收入)']}-{prices['高价商品 (面向高收入)']} 金币"
    )
    print(f"  奢侈品: {prices['高价商品 (面向高收入)']}+ 金币")


def main():
    """主函数"""
    print("📈 货币数据可视化分析工具")
    print("=" * 35)

    # 查找最新的分析文件
    analysis_file = find_latest_analysis_file()
    if not analysis_file:
        print("❌ 未找到分析数据文件，请先运行 coin_analysis.py")
        return

    print(f"📁 读取分析文件: {analysis_file}")

    # 读取数据
    try:
        with open(analysis_file, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ 读取文件失败: {e}")
        return

    summary = data["summary"]
    user_details = data["user_details"]
    analysis_time = data["analysis_time"]

    print(f"📅 分析时间: {analysis_time}")
    print(f"👥 总用户数: {summary['total_users']}")

    # 显示财富分布图表
    generate_text_chart(summary["wealth_distribution"], "财富分布")

    # 显示消费模式图表
    generate_text_chart(summary["spending_patterns"], "消费模式分布")

    # 用户细分分析
    user_segments = analyze_user_segments(user_details)
    generate_text_chart(user_segments, "用户等级分布")

    # 消费潜力分析
    affordability, total_coins = calculate_consumption_potential(user_details)
    generate_text_chart(affordability, "不同价格点的用户覆盖")

    print("\n💰 市场潜力分析:")
    print(f"  市场总金币量: {total_coins:,.0f} 金币")
    print(f"  平均每用户: {total_coins / len(user_details):,.1f} 金币")

    # 生成定价建议
    generate_pricing_recommendations(summary)

    # Top 10 富有用户分析
    top_users = sorted(user_details, key=lambda x: x["current_coin"], reverse=True)[:10]
    print("\n🏆 Top 10 富有用户:")
    for i, user in enumerate(top_users, 1):
        print(f"  {i:2d}. 用户 {user['user_id']}: {user['current_coin']:,.0f} 金币")

    # 市场建议
    print("\n🎯 市场策略建议:")

    wealthy_ratio = (
        summary["wealth_distribution"]["富裕 (1000+金币)"] / summary["total_users"]
    )
    if wealthy_ratio > 0.4:  # 40%以上是富裕用户
        print(f"  ✨ 市场成熟度高，富裕用户占 {wealthy_ratio * 100:.1f}%")
        print("     - 可以推出更多高价值商品")
        print("     - 考虑推出VIP会员服务")
        print("     - 开发订阅制或包月服务")

    low_income_ratio = (
        summary["wealth_distribution"]["贫困 (0金币)"]
        + summary["wealth_distribution"]["低收入 (1-100金币)"]
    ) / summary["total_users"]
    if low_income_ratio > 0.3:  # 30%以上是低收入用户
        print(f"  🎁 需要关注低收入用户 ({low_income_ratio * 100:.1f}%)")
        print("     - 增加免费获取金币的途径")
        print("     - 推出新手专享商品")
        print("     - 考虑签到奖励机制")

    print("\n✅ 可视化分析完成！")


if __name__ == "__main__":
    main()
