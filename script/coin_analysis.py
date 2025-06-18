#!/usr/bin/env python3
"""
货币数据分析脚本 - 使用 aiomysql 分析货币使用情况
分析用户的货币持有量和使用模式，为消费策略制定提供数据支持
"""

import asyncio
import os
import statistics
from dataclasses import dataclass

import aiomysql
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


@dataclass
class UserCoinStats:
    """用户货币统计数据"""

    user_id: str
    current_coin: float
    total_coin: float
    coin_ratio: float  # 当前金币/历史总金币比例
    activity_level: str  # 活跃度分类


@dataclass
class CoinAnalysisResult:
    """货币分析结果"""

    total_users: int
    avg_current_coin: float
    median_current_coin: float
    avg_total_coin: float
    median_total_coin: float
    active_users: int  # 当前有金币的用户数
    inactive_users: int  # 当前没有金币的用户数
    high_savers: int  # 储蓄型用户（保留率高）
    high_spenders: int  # 消费型用户（保留率低）
    wealth_distribution: dict[str, int]  # 财富分布
    spending_patterns: dict[str, int]  # 消费模式分布
    recommended_prices: dict[str, float]  # 推荐价格策略


class CoinAnalyzer:
    """货币数据分析器"""

    def __init__(self):
        self.db_config = self._parse_database_url()

    def _parse_database_url(self) -> dict:
        """解析数据库连接URL"""
        database_url = os.getenv("SQLALCHEMY_DATABASE_URL")
        if not database_url or not database_url.startswith("mysql+aiomysql://"):
            raise ValueError("请设置正确的 MySQL SQLALCHEMY_DATABASE_URL")

        # 解析 mysql+aiomysql://user:pass@host:port/db
        url = database_url.replace("mysql+aiomysql://", "")
        if "@" not in url:
            raise ValueError("数据库URL格式错误")

        auth_part, host_part = url.split("@", 1)
        user_pass = auth_part.split(":", 1)
        host_db = host_part.split("/", 1)

        user = user_pass[0]
        password = user_pass[1] if len(user_pass) > 1 else ""

        host_port = host_db[0].split(":", 1)
        host = host_port[0]
        port = int(host_port[1]) if len(host_port) > 1 else 3306
        database = host_db[1] if len(host_db) > 1 else ""

        return {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "db": database,
            "charset": "utf8mb4",
        }

    async def get_connection(self) -> aiomysql.Connection:
        """获取数据库连接"""
        return await aiomysql.connect(**self.db_config)

    async def fetch_coin_data(self) -> list[UserCoinStats]:
        """获取所有用户的货币数据"""
        conn = await self.get_connection()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                # 查询货币记录表
                await cursor.execute("""
                    SELECT user_id, coin, count_coin
                    FROM coin_coinrecord
                    ORDER BY count_coin DESC
                """)
                rows = await cursor.fetchall()

                user_stats = []
                for row in rows:
                    current_coin = float(row["coin"])
                    total_coin = float(row["count_coin"])

                    # 计算保留率（当前金币/历史总金币）
                    coin_ratio = current_coin / total_coin if total_coin > 0 else 0

                    # 根据保留率和金币量判断活跃度
                    if current_coin == 0:
                        activity_level = "inactive"  # 无金币用户
                    elif coin_ratio > 0.8:
                        activity_level = "saver"  # 储蓄型用户
                    elif coin_ratio < 0.2:
                        activity_level = "spender"  # 消费型用户
                    else:
                        activity_level = "moderate"  # 中等消费用户

                    user_stats.append(
                        UserCoinStats(
                            user_id=row["user_id"],
                            current_coin=current_coin,
                            total_coin=total_coin,
                            coin_ratio=coin_ratio,
                            activity_level=activity_level,
                        )
                    )

                return user_stats
        finally:
            conn.close()

    def analyze_coin_data(self, user_stats: list[UserCoinStats]) -> CoinAnalysisResult:
        """分析货币数据"""
        if not user_stats:
            raise ValueError("没有找到货币数据")

        # 基础统计
        current_coins = [user.current_coin for user in user_stats]
        total_coins = [user.total_coin for user in user_stats]

        total_users = len(user_stats)
        avg_current_coin = statistics.mean(current_coins)
        median_current_coin = statistics.median(current_coins)
        avg_total_coin = statistics.mean(total_coins)
        median_total_coin = statistics.median(total_coins)

        # 用户活跃度分析
        active_users = len([u for u in user_stats if u.current_coin > 0])
        inactive_users = total_users - active_users
        high_savers = len([u for u in user_stats if u.activity_level == "saver"])
        high_spenders = len([u for u in user_stats if u.activity_level == "spender"])

        # 财富分布分析
        wealth_distribution = {
            "贫困 (0金币)": len([u for u in user_stats if u.current_coin == 0]),
            "低收入 (1-100金币)": len(
                [u for u in user_stats if 0 < u.current_coin <= 100]
            ),
            "中等收入 (101-500金币)": len(
                [u for u in user_stats if 100 < u.current_coin <= 500]
            ),
            "高收入 (501-1000金币)": len(
                [u for u in user_stats if 500 < u.current_coin <= 1000]
            ),
            "富裕 (1000+金币)": len([u for u in user_stats if u.current_coin > 1000]),
        }

        # 消费模式分析
        spending_patterns = {
            "储蓄型 (保留率>80%)": high_savers,
            "中等消费型 (保留率20-80%)": len(
                [u for u in user_stats if u.activity_level == "moderate"]
            ),
            "消费型 (保留率<20%)": high_spenders,
            "无活动": inactive_users,
        }

        # 推荐价格策略
        recommended_prices = self._calculate_price_recommendations(
            user_stats, avg_current_coin, median_current_coin
        )

        return CoinAnalysisResult(
            total_users=total_users,
            avg_current_coin=avg_current_coin,
            median_current_coin=median_current_coin,
            avg_total_coin=avg_total_coin,
            median_total_coin=median_total_coin,
            active_users=active_users,
            inactive_users=inactive_users,
            high_savers=high_savers,
            high_spenders=high_spenders,
            wealth_distribution=wealth_distribution,
            spending_patterns=spending_patterns,
            recommended_prices=recommended_prices,
        )

    def _calculate_price_recommendations(
        self, user_stats: list[UserCoinStats], avg_coin: float, median_coin: float
    ) -> dict[str, float]:
        """计算推荐价格策略"""
        active_users = [u for u in user_stats if u.current_coin > 0]

        if not active_users:
            return {"低价商品": 10, "中价商品": 50, "高价商品": 100, "奢侈品": 200}

        active_coins = [u.current_coin for u in active_users]

        # 基于用户财富分布的价格策略
        p25 = statistics.quantiles(active_coins, n=4)[0]  # 25%分位数
        p50 = statistics.median(active_coins)  # 50%分位数（中位数）
        p75 = statistics.quantiles(active_coins, n=4)[2]  # 75%分位数

        return {
            "低价商品 (面向所有用户)": round(p25 * 0.1, 1),  # 25%分位数的10%
            "中价商品 (面向中等收入)": round(p50 * 0.2, 1),  # 中位数的20%
            "高价商品 (面向高收入)": round(p75 * 0.3, 1),  # 75%分位数的30%
            "奢侈品 (面向富裕用户)": round(max(active_coins) * 0.1, 1),  # 最大值的10%
            "促销价格": round(p25 * 0.05, 1),  # 25%分位数的5%，用于促销
        }

    def print_analysis_report(self, result: CoinAnalysisResult):
        """打印分析报告"""
        print("=" * 60)
        print("🪙 货币系统数据分析报告")
        print("=" * 60)

        print("\n📊 基础统计:")
        print(f"  总用户数: {result.total_users}")
        print(
            f"  活跃用户数: {result.active_users} ({result.active_users / result.total_users * 100:.1f}%)"
        )
        print(
            f"  非活跃用户数: {result.inactive_users} ({result.inactive_users / result.total_users * 100:.1f}%)"
        )

        print("\n💰 当前金币分析:")
        print(f"  平均金币: {result.avg_current_coin:.1f}")
        print(f"  中位数金币: {result.median_current_coin:.1f}")

        print("\n📈 历史金币分析:")
        print(f"  平均历史总金币: {result.avg_total_coin:.1f}")
        print(f"  中位数历史总金币: {result.median_total_coin:.1f}")

        print("\n👥 用户行为分析:")
        print(
            f"  储蓄型用户: {result.high_savers} ({result.high_savers / result.total_users * 100:.1f}%)"
        )
        print(
            f"  消费型用户: {result.high_spenders} ({result.high_spenders / result.total_users * 100:.1f}%)"
        )

        print("\n💎 财富分布:")
        for category, count in result.wealth_distribution.items():
            percentage = count / result.total_users * 100
            print(f"  {category}: {count}人 ({percentage:.1f}%)")

        print("\n🛒 消费模式分布:")
        for pattern, count in result.spending_patterns.items():
            percentage = count / result.total_users * 100
            print(f"  {pattern}: {count}人 ({percentage:.1f}%)")

        print("\n💡 推荐价格策略:")
        for item_type, price in result.recommended_prices.items():
            print(f"  {item_type}: {price} 金币")

        print("\n📝 消费策略建议:")
        self._print_consumption_recommendations(result)

        print("=" * 60)

    def _print_consumption_recommendations(self, result: CoinAnalysisResult):
        """打印消费策略建议"""
        active_rate = result.active_users / result.total_users
        saver_rate = result.high_savers / result.total_users
        spender_rate = result.high_spenders / result.total_users

        print("\n  基于数据分析的建议:")

        if active_rate < 0.5:
            print(f"  🎯 用户活跃度较低 ({active_rate * 100:.1f}%)，建议:")
            print("     - 增加金币获取途径")
            print("     - 推出低价位商品吸引参与")
            print("     - 考虑新手奖励机制")

        if saver_rate > 0.3:
            print(f"  💎 储蓄型用户较多 ({saver_rate * 100:.1f}%)，建议:")
            print("     - 推出限时高价值商品")
            print("     - 增加稀有物品激励消费")
            print("     - 考虑通胀机制或金币过期")

        if spender_rate > 0.3:
            print(f"  🛍️ 消费型用户较多 ({spender_rate * 100:.1f}%)，建议:")
            print("     - 保持商品供应充足")
            print("     - 推出会员制度或忠诚度奖励")
            print("     - 考虑分期付款或打折活动")

        avg_coin = result.avg_current_coin
        if avg_coin < 100:
            print(f"  📉 平均金币较低 ({avg_coin:.1f})，建议:")
            print("     - 主推低价商品 (10-50金币)")
            print("     - 增加日常任务奖励")
        elif avg_coin > 500:
            print(f"  📈 平均金币较高 ({avg_coin:.1f})，建议:")
            print("     - 可以推出更多高价商品")
            print("     - 考虑金币消耗活动")


async def main():
    """主函数"""
    print("🔍 开始分析货币数据...")

    try:
        analyzer = CoinAnalyzer()

        # 获取数据
        print("📥 正在获取用户货币数据...")
        user_stats = await analyzer.fetch_coin_data()

        if not user_stats:
            print("❌ 未找到任何货币数据")
            return

        print(f"✅ 成功获取 {len(user_stats)} 条用户数据")

        # 分析数据
        print("🔬 正在分析数据...")
        result = analyzer.analyze_coin_data(user_stats)

        # 输出报告
        analyzer.print_analysis_report(result)

        # 保存详细数据到文件
        await save_detailed_analysis(user_stats, result)

    except Exception as e:
        print(f"❌ 分析过程中出错: {e}")
        import traceback

        traceback.print_exc()


async def save_detailed_analysis(
    user_stats: list[UserCoinStats], result: CoinAnalysisResult
):
    """保存详细分析数据到文件"""
    import json
    from datetime import datetime

    # 准备导出数据
    export_data = {
        "analysis_time": datetime.now().isoformat(),
        "summary": {
            "total_users": result.total_users,
            "avg_current_coin": result.avg_current_coin,
            "median_current_coin": result.median_current_coin,
            "active_users": result.active_users,
            "wealth_distribution": result.wealth_distribution,
            "spending_patterns": result.spending_patterns,
            "recommended_prices": result.recommended_prices,
        },
        "user_details": [
            {
                "user_id": user.user_id,
                "current_coin": user.current_coin,
                "total_coin": user.total_coin,
                "coin_ratio": user.coin_ratio,
                "activity_level": user.activity_level,
            }
            for user in user_stats
        ],
    }

    filename = f"coin_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)

    print(f"\n💾 详细分析数据已保存到: {filename}")


if __name__ == "__main__":
    asyncio.run(main())
