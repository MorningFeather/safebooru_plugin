# Safebooru动漫图片搜索插件

## 功能介绍

这是一个为MaiBot开发的Safebooru图片搜索插件，支持多种交互方式：

- **命令模式**: 使用 `/safebooru [标签]` 或 `/sb [标签]` 搜索图片
- **自然语言模式**: 智能识别"发图"、"来张图"等自然语言请求
- **LLM工具模式**: 供LLM自动调用的工具函数

## 功能特性

- ✅ Safebooru API集成
- ✅ 多种交互方式（Command/Action/Tool）
- ✅ 智能标签提取和映射
- ✅ 图片格式自动转换
- ✅ 人格化回复生成
- ✅ 完善的错误处理
- ✅ 配置文件支持
- ✅ 内容安全过滤

## 安装方法

### 1. 安装依赖

```bash
pip install aiohttp pillow
```

### 2. 配置插件

1. 复制配置文件模板：
```bash
cp config.example.toml config.toml
```

2. 编辑 `config.toml` 文件，根据需要调整配置：

```toml
[plugin]
config_version = "1.0.0"
enabled = true

[safebooru]
default_tags = "anime cute"
max_results = 3
rating = "safe"
timeout = 30

[response]
show_tags = false
personality_style = "cute"
enable_natural_search = true
```

### 3. 启动插件

将插件目录放置在MaiBot的 `plugins/` 目录下，启动MaiBot时插件会自动加载。

## 使用方法

### 命令模式

```bash
/safebooru cat cute
/sb anime
/safebooru 樱花 雪景
```

### 自然语言模式

```
发张猫猫的图片
来张动漫图
给我来点二次元图片
发张风景壁纸
```

### LLM工具模式

LLM可以自动调用 `safebooru_search` 工具来搜索图片。

## 配置说明

### [plugin] 部分
- `enabled`: 是否启用插件
- `config_version`: 配置文件版本

### [safebooru] 部分
- `default_tags`: 默认搜索标签
- `max_results`: 搜索结果最大数量
- `rating`: 图片等级限制 (safe/questionable/explicit)
- `timeout`: 请求超时时间（秒）

### [response] 部分
- `show_tags`: 是否显示图片标签信息
- `personality_style`: 人格风格 (cute/cool/elegant)
- `enable_natural_search`: 是否启用自然语言搜索

## 支持的中文关键词映射

插件支持中文关键词到英文标签的自动映射：

| 中文 | 英文标签 |
|------|----------|
| 猫 | cat |
| 狗 | dog |
| 兔子 | rabbit |
| 狐狸 | fox |
| 狼 | wolf |
| 龙 | dragon |
| 天使 | angel |
| 恶魔 | demon |
| 魔法 | magic |
| 学校 | school |
| 泳装 | swimsuit |
| 和服 | kimono |
| 猫耳 | cat_ears |
| 尾巴 | tail |
| 可爱 | cute |
| 美少女 | beautiful_girl |
| 少年 | boy |
| 少女 | girl |
| 风景 | landscape |
| 夜景 | night |
| 樱花 | sakura cherry_blossom |
| 雨 | rain |
| 雪 | snow |

## 错误处理

插件包含完善的错误处理机制：

- 网络超时处理
- API请求失败处理
- 图片下载失败处理
- 格式转换错误处理
- 无效标签处理

## 安全特性

- 默认只搜索安全级别图片 (rating:safe)
- 支持内容过滤配置
- 图片格式验证和处理
- 异常情况下的降级处理

## 测试

运行测试脚本验证插件功能：

```bash
# 基础测试（推荐）
python basic_test.py

# 完整测试（需要MaiBot环境）
python test_plugin.py
```

## 故障排除

### 常见问题

1. **模块导入错误**
   ```
   ModuleNotFoundError: No module named 'aiohttp'
   ```
   解决方案：安装依赖 `pip install aiohttp pillow`

2. **图片下载失败**
   - 检查网络连接
   - 确认Safebooru网站可访问
   - 检查防火墙设置

3. **搜索无结果**
   - 尝试使用不同的标签
   - 检查标签拼写
   - 确认标签存在

4. **配置文件错误**
   - 确认TOML格式正确
   - 检查配置项拼写
   - 参考config.example.toml

### 调试模式

启用调试日志：

```toml
[plugin]
enabled = true
debug = true  # 启用调试日志
```

## 开发信息

- **插件版本**: 1.0.0
- **兼容MaiBot版本**: 0.8.0+
- **开发语言**: Python 3.8+
- **许可证**: GPL-v3.0-or-later

## 更新日志

### v1.0.0 (2024-12-24)
- ✨ 初始版本发布
- ✅ 支持Safebooru API集成
- ✅ 实现Command/Action/Tool三种组件
- ✅ 添加中文关键词映射
- ✅ 完善错误处理机制
- ✅ 添加人格化回复

## 贡献

欢迎提交Issue和Pull Request来改进这个插件！

## 许可证

GPL-v3.0-or-later