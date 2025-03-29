# U1bot

U1bot 是一个基于 Nonebot2 框架下的 QQ 机器人项目，致力于在 QQ 中丰富化。欢迎大家贡献代码、提出问题或建议。本项目是基于开源精神构建的，感谢所有贡献者！

> 欢迎加入我们的 用户群（713478803）

## 如何开始

### CLI 玩家

作者平时都这么玩，一般会确保这个方法是可用的

1. 安装 poetry： `pip install poetry`
2. 安装依赖： `poetry install`
3. 运行： `poetry run python bot.py`

### 折腾类玩家

在配置的时候会有点抽象...

1. 确保已有一个可用的 Nonebot2 环境，要求使用虚拟环境。
2. 复制并按文件注释修改配置文件 `.env`
3. 复制 `src/plugins` 下所有文件到对应位置，并在 `pyproject.toml` 中注明位置
4. 使用你喜欢的工具安装好依赖和适配器（`nb adapter install nonebot-adapter-onebot`）
5. 使用 `nb-cli` 启动（`nb run` 或先生成入口文件并用 `python bot.py`启动）

### 不喜折腾玩家

你可以联系我们提供远程安装服务。

## 必填环境变量

1. `QWEATHER_APIKEY`：和风天气的 API Key，[注册地址](https://dev.qweather.com/)
2. `bilibili_cookie`：B 站用户 Cookie，用于获取用户信息，[获取方式](#cookie-获取方式)


### Cookie 获取方式

1. 在 `.env.xxx` 文件中添加 B 站用户 Cookie：

2. 获取 Cookie 的方式：

- 打开浏览器开发工具 `F12`
- 在开发者工具中查看 `www.bilibili.com` 请求的响应头
- 找到形如 `SESSDATA=xxx;` 的字段
- 复制整个字段，如下图所示：

<div align="left">
  <img src="https://s2.loli.net/2022/07/19/AIBmd2Z9V5YwlkF.png" width="500" />
</div>
