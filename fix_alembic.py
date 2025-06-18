#!/usr/bin/env python3
import asyncio
import os

import aiomysql
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


async def fix_alembic_version():
    # 从环境变量获取数据库配置
    database_url = os.getenv("SQLALCHEMY_DATABASE_URL")
    if not database_url:
        print("SQLALCHEMY_DATABASE_URL 未设置")
        return

    # 解析数据库 URL: mysql+aiomysql://user:pass@host:port/db
    if database_url.startswith("mysql+aiomysql://"):
        url_without_driver = database_url.replace("mysql+aiomysql://", "")

        # 分解 URL
        if "@" in url_without_driver:
            auth_part, host_db_part = url_without_driver.split("@", 1)
            if ":" in auth_part:
                user, password = auth_part.split(":", 1)
            else:
                user = auth_part
                password = ""
        else:
            user = "root"
            password = ""
            host_db_part = url_without_driver

        if "/" in host_db_part:
            host_port, database = host_db_part.split("/", 1)
        else:
            host_port = host_db_part
            database = "test"

        if ":" in host_port:
            host, port = host_port.split(":", 1)
            port = int(port)
        else:
            host = host_port
            port = 3306

        print(f"连接数据库: {host}:{port}/{database}")

        try:
            # 连接数据库
            connection = await aiomysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                db=database,
                charset="utf8mb4",
            )

            cursor = await connection.cursor()

            # 清理 alembic_version 表
            await cursor.execute("DELETE FROM alembic_version")
            print("清理了旧的 alembic_version 记录")

            # 插入正确的版本
            await cursor.execute(
                "INSERT INTO alembic_version (version_num) VALUES (%s)",
                ("d03e28cd244a",),
            )
            print("插入了正确的版本记录: d03e28cd244a")

            await connection.commit()

            # 验证结果
            await cursor.execute("SELECT * FROM alembic_version")
            versions = await cursor.fetchall()
            print("当前版本记录:")
            for version in versions:
                print(f"  - {version[0]}")

            await cursor.close()
            connection.close()

        except Exception as e:
            print(f"数据库操作错误: {e}")
    else:
        print("不支持的数据库 URL 格式")


if __name__ == "__main__":
    asyncio.run(fix_alembic_version())
