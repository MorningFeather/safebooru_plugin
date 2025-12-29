import asyncio
import random
import re
import base64
import io
import json
import time
from typing import List, Tuple, Type, Any, Dict, Optional
from urllib.parse import quote

import aiohttp
from PIL import Image

from src.config.config import global_config
from src.plugin_system import (
    BasePlugin,
    register_plugin,
    BaseAction,
    BaseCommand,
    BaseTool,
    ComponentInfo,
    ActionActivationType,
    ConfigField,
    ToolParamType,
    ReplyContentType,
)
from src.plugin_system.apis import generator_api, message_api
from src.common.logger import get_logger

logger = get_logger("safebooru_plugin")


class SafebooruAPI:
    """Safebooru API交互类"""
    
    BASE_URL = "https://safebooru.org/index.php"
    TAG_API_URL = "https://safebooru.org/index.php?page=dapi&s=tag&q=index"
    
    # 高置信度白名单 (Fast-Path Bypass)
    FAST_PATH_TAGS = {
        "shirakami_fubuki", "houshou_marine", "minato_aqua", "usada_pekora",
        "hatsune_miku", "megurine_luka", "kagamine_rin", "kagamine_len",
        "hu_tao_(genshin_impact)", "raiden_shogun_(genshin_impact)",
        "ganyu_(genshin_impact)", "keqing_(genshin_impact)"
    }

    # 关键词映射表
    TAG_MAPPINGS = {
        "猫": "cat",
        "狗": "dog",
        "兔子": "rabbit",
        "狐狸": "fox",
        "狼": "wolf",
        "龙": "dragon",
        "天使": "angel",
        "恶魔": "demon",
        "魔法": "magic",
        "学校": "school",
        "泳装": "swimsuit",
        "和服": "kimono",
        "猫耳": "cat_ears",
        "尾巴": "tail",
        "可爱": "cute",
        "美少女": "beautiful_girl",
        "少年": "boy",
        "少女": "girl",
        "风景": "landscape",
        "夜景": "night",
        "樱花": "sakura cherry_blossom",
        "雨": "rain",
        "雪": "snow",
        "初音": "hatsune_miku",
        "未来": "hatsune_miku",
        "miku": "hatsune_miku",
        "天依": "luo_tianyi",
        "洛天依": "luo_tianyi",
        "言和": "yan_he",
        "乐正绫": "yuezheng_ling",
        "重音": "kasane_teto",
        "teto": "kasane_teto",
        "灵梦": "hakurei_reimu",
        "魔理沙": "kirisame_marisa",
        "春日步": "kasuga_ayumu",
        "大阪": "kasuga_ayumu",
        "芙兰": "flandre_scarlet",
        "蕾米": "remilia_scarlet",
        "爱蜜莉雅": "emilia_(re:zero)",
        "雷姆": "rem_(re:zero)",
        "拉姆": "ram_(re:zero)",
        "胡桃": "hu_tao_(genshin_impact)",
        "刻晴": "keqing_(genshin_impact)",
        "甘雨": "ganyu_(genshin_impact)",
        "纳西妲": "nahida_(genshin_impact)",
        "雷电将军": "raiden_shogun_(genshin_impact)",
        "一起": "multiple_girls",
        "合照": "multiple_girls",
        "白发": "white_hair",
        "黑发": "black_hair",
        "金发": "blonde_hair",
        "蓝发": "blue_hair",
        "红发": "red_hair",
        "绿发": "green_hair",
        "粉发": "pink_hair",
        "单人": "solo",
        "独照": "solo",
        "高清": "highres",
        "壁纸": "wallpaper",
        "大图": "highres",
        "萝莉": "loli",
        "御姐": "onee-san",
        "女仆": "maid",
        "护士": "nurse",
        "警察": "police",
        "医生": "doctor",
        "老师": "teacher",
        "学生": "student",
        "制服": "uniform",
        "水手服": "sailor_uniform",
        "运动服": "gym_uniform",
        "死库水": "school_swimsuit",
        "旗袍": "cheongsam",
        "哥特": "gothic",
        "洛丽塔": "lolita",
        "森林": "forest",
        "大海": "sea",
        "沙滩": "beach",
        "天空": "sky",
        "云": "clouds",
        "夕阳": "sunset",
        "星星": "stars",
        "月亮": "moon",
        "花": "flower",
        "城市": "city",
        "街道": "street",
        "室内": "indoor",
        "室外": "outdoor",
        "特写": "close-up",
        "全身": "full_body",
        "侧面": "profile",
        "背面": "back",
        "坐": "sitting",
        "站": "standing",
        "躺": "lying",
        "笑": "smile",
        "哭": "crying",
        "害羞": "blush",
        "生气": "angry",
        "睡觉": "sleeping",
        "吃": "eating",
        "喝": "drinking",
        "玩": "playing",
        "看": "looking_at_viewer",
    }

    @staticmethod
    def extract_tags(text: str) -> str:
        """从文本中提取并转换标签"""
        if not text:
            return ""
        text = text.lower()
        found_tags = set()
        
        # 1. 中文映射
        for chinese, english in SafebooruAPI.TAG_MAPPINGS.items():
            if chinese in text:
                for tag in english.split():
                    found_tags.add(tag)
        
        # 2. 英文提取 (包含下划线，防止标签被拆分)
        # 匹配包含字母、数字、下划线的单词
        english_words = re.findall(r'\b[a-zA-Z0-9_]+\b', text)
        stop_words = {'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'image', 'picture', 'photo', 'search'}
        
        for word in english_words:
            if word not in stop_words and not word.isdigit() and len(word) > 2:
                found_tags.add(word)
        
        return ' '.join(list(found_tags))

    @staticmethod
    async def validate_tags(tags_str: str, timeout_val: int = 15) -> Dict[str, Any]:
        """
        VBS 预校验层：对输入关键词进行实体对齐和分类
        """
        tags = tags_str.split()
        results = {
            "validated_tags": [],
            "ambiguous_entities": {}, # tag -> [candidates]
            "low_entropy": False,
            "fast_path": True
        }
        
        # 弱语义识别
        weak_semantics = {"girl", "boy", "anime", "solo", "highres", "wallpaper", "cute"}
        if all(t.lower() in weak_semantics for t in tags):
            results["low_entropy"] = True
            results["fast_path"] = False

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_val)) as session:
            for tag in tags:
                if tag.lower() in SafebooruAPI.FAST_PATH_TAGS:
                    results["validated_tags"].append(tag)
                    continue
                
                results["fast_path"] = False
                # 调用 Tag API 校验
                url = f"{SafebooruAPI.TAG_API_URL}&name={quote(tag)}&json=1"
                try:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if not data:
                                # 模糊匹配尝试
                                fuzzy_url = f"{SafebooruAPI.TAG_API_URL}&name_pattern={quote(tag)}*&order=count&json=1"
                                async with session.get(fuzzy_url) as f_resp:
                                    if f_resp.status == 200:
                                        f_data = await f_resp.json()
                                        if f_data:
                                            # 实体冲突检测：如果匹配到多个热门实体
                                            candidates = f_data if isinstance(f_data, list) else [f_data]
                                            # 过滤掉非 ASCII 标签
                                            candidates = [c for c in candidates if all(ord(char) < 128 for char in c.get('name', ''))]
                                            if len(candidates) > 1:
                                                results["ambiguous_entities"][tag] = candidates[:5]
                                            elif candidates:
                                                results["validated_tags"].append(candidates[0]['name'])
                            else:
                                tag_info = data[0] if isinstance(data, list) else data
                                results["validated_tags"].append(tag_info['name'])
                except Exception as e:
                    logger.error(f"[Safebooru] Tag校验失败 ({tag}): {e}")
                    # 容错：保留原标签
                    results["validated_tags"].append(tag)
        
        return results

    @staticmethod
    async def search_images(tags: str, limit: int = 1, rating: str = "safe", timeout_val: int = 30) -> List[Dict]:
        """
        从Safebooru搜索图片
        
        Args:
            tags: 搜索标签，多个标签用空格分隔
            limit: 返回结果数量限制
            rating: 图片等级限制 (safe, questionable, explicit)
            timeout_val: 超时时间
            
        Returns:
            List[Dict]: 图片信息列表
        """
        try:
            # 处理标签：将逗号替换为空格，清理多余空格
            # 同时过滤掉非 ASCII 字符，因为 Safebooru DAPI 不支持中文标签
            processed_tags = tags.replace(',', ' ')
            processed_tags = "".join([c for c in processed_tags if ord(c) < 128])
            processed_tags = processed_tags.strip()
            processed_tags = re.sub(r'\s+', ' ', processed_tags)
            
            # 如果过滤后没有有效标签，使用默认标签
            if not processed_tags:
                processed_tags = "anime cute"
            
            # 注意：Safebooru DAPI 不支持 order:score 语法
            # 随机选择一个页码进行搜索，不再进行自动重试
            pid = random.randint(0, 10)
            
            timeout = aiohttp.ClientTimeout(total=timeout_val)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 构建查询参数
                params = {
                    "page": "dapi",
                    "s": "post",
                    "q": "index",
                    "tags": f"{processed_tags} rating:{rating}",
                    "limit": min(limit, 100),
                    "pid": pid,
                    "json": 1
                }
                
                # 构建URL
                url = f"{SafebooruAPI.BASE_URL}?" + "&".join([f"{k}={quote(str(v))}" for k, v in params.items()])
                logger.debug(f"[Safebooru] 尝试搜索 (pid={pid}): {url}")
                
                async with session.get(url) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            if data:
                                image_list = data if isinstance(data, list) else [data]
                                logger.debug(f"[Safebooru] 在 pid={pid} 找到 {len(image_list)} 张图片")
                                return image_list
                        except Exception:
                            text = await response.text()
                            if text.strip():
                                logger.warning(f"[Safebooru] pid={pid} 响应解析失败: {text[:100]}")
                    else:
                        logger.error(f"[Safebooru] pid={pid} API请求失败: HTTP {response.status}")
            
            logger.info(f"[Safebooru] 未找到图片: {processed_tags}")
            return []
                        
        except asyncio.TimeoutError:
            logger.error("[Safebooru] 请求超时")
            return []
        except aiohttp.ClientError as e:
            logger.error(f"[Safebooru] 网络错误: {e}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"[Safebooru] JSON解析错误: {e}")
            return []
        except Exception as e:
            logger.error(f"[Safebooru] 未知错误: {e}")
            return []
    
    @staticmethod
    async def download_image(image_url: str) -> Optional[str]:
        """
        下载图片并返回base64编码
        
        Args:
            image_url: 图片URL
            
        Returns:
            Optional[str]: base64编码的图片数据，失败返回None
        """
        try:
            # 注意：download_image 是静态方法，无法直接访问 get_config
            # 我们在调用处处理超时，或者这里给一个较大的默认值
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        
                        # 验证图片数据
                        try:
                            img = Image.open(io.BytesIO(image_data))
                            img.verify()  # 验证图片完整性
                            
                            # 重新打开图片（verify会关闭文件）
                            img = Image.open(io.BytesIO(image_data))
                            
                            # 转换为RGB格式（处理RGBA等格式）
                            if img.mode in ('RGBA', 'LA', 'P'):
                                background = Image.new('RGB', img.size, (255, 255, 255))
                                if img.mode == 'P':
                                    img = img.convert('RGBA')
                                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                                img = background
                            
                            # 保存为JPEG格式以减小大小
                            buffer = io.BytesIO()
                            img.save(buffer, format='JPEG', quality=85, optimize=True)
                            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                            
                            logger.debug(f"[Safebooru] 图片下载成功，大小: {len(image_base64)} 字符")
                            return image_base64
                            
                        except Exception as img_error:
                            logger.error(f"[Safebooru] 图片处理失败: {img_error}")
                            return None
                    else:
                        logger.error(f"[Safebooru] 图片下载失败: HTTP {response.status}")
                        return None
                        
        except asyncio.TimeoutError:
            logger.error("[Safebooru] 图片下载超时")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"[Safebooru] 图片下载网络错误: {e}")
            return None
        except Exception as e:
            logger.error(f"[Safebooru] 图片下载未知错误: {e}")
            return None


class SafebooruCommand(BaseCommand):
    """Safebooru图片搜索命令组件"""
    
    command_name = "safebooru"
    command_description = "从Safebooru搜索动漫图片"
    
    # 匹配 /safebooru [标签] 或 /sb [标签]
    command_pattern = r"^(?:/safebooru|/sb)\s*(.*)$"
    
    async def _send_personality_text(self, intent_description: str, context_data: Optional[Dict] = None) -> None:
        """
        完全通过人格化逻辑生成并发送文本。
        不再使用硬编码模板，而是将意图描述和上下文交给 generator_api 处理。
        """
        try:
            # 构建一个纯事实的“草稿”，仅作为 LLM 理解意图的参考
            # 最终输出将完全由 LLM 根据人格设定重写
            raw_draft = f"[INTENT: {intent_description}]"
            if context_data:
                raw_draft += f" [CONTEXT: {json.dumps(context_data, ensure_ascii=False)}]"

            success, llm_response = await generator_api.rewrite_reply(
                chat_stream=self.chat_stream,
                raw_reply=raw_draft,
                reason=f"Safebooru插件交互: {intent_description}",
                request_type="safebooru_personality"
            )
            if success and llm_response and llm_response.content:
                await self.send_text(llm_response.content)
            else:
                # 降级处理：如果重写失败，至少发送一个基本的意图描述（虽然不理想，但保证了交互不中断）
                logger.warning(f"[Safebooru] 人格化重写失败，使用降级输出: {intent_description}")
                await self.send_text(f"（正在处理: {intent_description}）")
        except Exception as e:
            logger.error(f"[Safebooru] 人格化文本生成失败: {e}")

    def _is_explicitly_triggered(self) -> bool:
        """
        检查是否满足显式触发条件：
        1. 消息中包含机器人昵称
        2. 消息中有 @机器人 (is_mentioned)
        3. 当前处于已被显式唤醒后的上下文连贯对话中
        """
        # 1. 检查 @提及
        if getattr(self.action_message, 'is_mentioned', False):
            logger.debug("[Safebooru] 触发校验通过: 检测到 @提及")
            return True
            
        # 2. 检查昵称
        bot_nickname = global_config.bot.nickname
        if bot_nickname and bot_nickname in self.action_message.processed_plain_text:
            logger.debug(f"[Safebooru] 触发校验通过: 检测到昵称 '{bot_nickname}'")
            return True
            
        # 3. 检查上下文连贯性
        current_time = time.time()
        last_active = getattr(self.chat_stream, 'last_active_time', 0)
        if current_time - last_active < 60:
             logger.debug(f"[Safebooru] 触发校验通过: 检测到活跃上下文 (距离上次活跃 {current_time - last_active:.1f}s)")
             return True

        return False

    async def execute(self) -> Tuple[bool, str, int]:
        """执行Safebooru图片搜索命令"""
        try:
            # 实施严格的显式触发过滤
            if not self._is_explicitly_triggered():
                logger.debug("[Safebooru] 未检测到显式唤醒或有效上下文，插件保持静默")
                return False, "未显式触发，保持静默", 2

            match = re.match(self.command_pattern, self.action_message.processed_plain_text, re.IGNORECASE)
            if not match:
                await self._send_personality_text("告知用户命令格式错误，应为 /safebooru [标签]")
                return False, "命令格式错误", 2
            
            raw_input = match.group(1).strip()
            tags = SafebooruAPI.extract_tags(raw_input) if raw_input else self.get_config("default_tags", "anime cute")
            
            # --- VBS 预校验与消歧逻辑 ---
            vbs_state = getattr(self.chat_stream, 'safebooru_vbs_state', {"count": 0, "pending_tag": None})
            vbs_results = await SafebooruAPI.validate_tags(tags)
            
            if vbs_results["ambiguous_entities"] and vbs_state["count"] < 3:
                ambiguous_tag = list(vbs_results["ambiguous_entities"].keys())[0]
                candidates = vbs_results["ambiguous_entities"][ambiguous_tag]
                vbs_state["count"] += 1
                vbs_state["pending_tag"] = ambiguous_tag
                self.chat_stream.safebooru_vbs_state = vbs_state
                await self._send_personality_text("检测到标签歧义，请求用户澄清", {
                    "tag": ambiguous_tag,
                    "candidates": [c['name'] for c in candidates]
                })
                return True, f"等待用户消歧: {ambiguous_tag}", 2

            if vbs_results["low_entropy"]:
                await self._send_personality_text("告知用户语义太弱，请求补充更多特征", {"input": tags})
                return True, "语义不足，已请求补充", 2

            final_tags = " ".join(vbs_results["validated_tags"])
            if vbs_state["count"] >= 3:
                for t, candidates in vbs_results["ambiguous_entities"].items():
                    final_tags += f" {candidates[0]['name']}"
                await self._send_personality_text("告知用户由于多次尝试未果，已自动选择最匹配的标签执行搜索", {"tags": final_tags})
            
            if hasattr(self.chat_stream, 'safebooru_vbs_state'):
                del self.chat_stream.safebooru_vbs_state

            # 1. 告知正在搜索 (完全人格化)
            await self._send_personality_text("收到搜图请求，以自然语气告知用户正在寻找相关图片", {"tags": final_tags})
            
            # 2. 搜索图片
            search_limit = max(self.get_config("max_results", 3) * 3, 10)
            rating = self.get_config("rating", "safe")
            timeout_val = self.get_config("timeout", 30)
            images = await SafebooruAPI.search_images(final_tags, search_limit, rating, timeout_val)
            
            if images:
                # 3. 随机选择并下载
                selected_image = random.choice(images)
                image_url = selected_image.get('file_url') or selected_image.get('sample_url')
                
                if image_url:
                    image_base64 = await SafebooruAPI.download_image(image_url)
                    if image_base64:
                        # 4. 发送图片
                        success = await self.send_image(image_base64)
                        if success:
                            # 5. 成功发送图片后，不再主动发送人格化描述，交由主大脑处理
                            return True, f"成功发送图片: {tags}", 2
                        else:
                            await self._send_personality_text("告知图片发送失败（可能文件过大）并询问是否重试")
                    else:
                        await self._send_personality_text("告知图片下载失败并询问是否重试")
                else:
                    await self._send_personality_text("告知图片链接失效并询问是否重试")
            else:
                # 搜索失败时，不再主动发送人格化描述，交由主大脑处理
                pass
            
            return True, "执行完毕，等待用户反馈", 2
                
        except Exception as e:
            logger.error(f"[SafebooruCommand] 执行错误: {e}")
            await self._send_personality_text("告知发生未知错误导致搜索中断，并询问是否重试")
            return True, f"执行错误: {e}", 2


class SafebooruAction(BaseAction):
    """Safebooru图片搜索Action组件 - 处理自然语言请求"""
    
    action_name = "safebooru_search"
    action_description = "智能识别发图请求并搜索图片"
    
    # 改为 ALWAYS 激活，让 LLM 根据语义智能判断是否触发
    activation_type = ActionActivationType.ALWAYS
    
    action_parameters = {"search_tags": "搜索的图片标签 (英文, 如 'cat', 'girl', 'landscape')"}
    action_require = [
        "只有在用户明确要求机器人发图、看图或需要动漫图片时才使用",
        "如果用户只是提到图片但没有明确的发图指令，不要使用"
    ]
    associated_types = ["text"]
    
    async def _send_personality_text(self, intent_description: str, context_data: Optional[Dict] = None) -> None:
        """
        完全通过人格化逻辑生成并发送文本。
        不再使用硬编码模板，而是将意图描述和上下文交给 generator_api 处理。
        """
        try:
            raw_draft = f"[INTENT: {intent_description}]"
            if context_data:
                raw_draft += f" [CONTEXT: {json.dumps(context_data, ensure_ascii=False)}]"

            success, llm_response = await generator_api.rewrite_reply(
                chat_stream=self.chat_stream,
                raw_reply=raw_draft,
                reason=f"Safebooru插件交互: {intent_description}",
                request_type="safebooru_personality"
            )
            if success and llm_response and llm_response.content:
                await self.send_text(llm_response.content)
            else:
                logger.warning(f"[Safebooru] 人格化重写失败，使用降级输出: {intent_description}")
                await self.send_text(f"（正在处理: {intent_description}）")
        except Exception as e:
            logger.error(f"[Safebooru] 人格化文本生成失败: {e}")

    def _is_explicitly_triggered(self) -> bool:
        """
        检查是否满足显式触发条件：
        1. 消息中包含机器人昵称
        2. 消息中有 @机器人 (is_mentioned)
        3. 当前处于已被显式唤醒后的上下文连贯对话中
        """
        # 1. 检查 @提及
        if getattr(self.action_message, 'is_mentioned', False):
            logger.debug("[Safebooru] 触发校验通过: 检测到 @提及")
            return True
            
        # 2. 检查昵称
        bot_nickname = global_config.bot.nickname
        if bot_nickname and bot_nickname in self.action_message.processed_plain_text:
            logger.debug(f"[Safebooru] 触发校验通过: 检测到昵称 '{bot_nickname}'")
            return True
            
        # 3. 检查上下文连贯性
        # 如果最近 60 秒内该聊天流有活跃记录，认为处于连贯对话中
        current_time = time.time()
        last_active = getattr(self.chat_stream, 'last_active_time', 0)
        if current_time - last_active < 60:
             logger.debug(f"[Safebooru] 触发校验通过: 检测到活跃上下文 (距离上次活跃 {current_time - last_active:.1f}s)")
             return True

        return False

    async def execute(self) -> Tuple[bool, str]:
        """执行智能图片搜索"""
        try:
            # 实施严格的显式触发过滤
            if not self._is_explicitly_triggered():
                logger.debug("[Safebooru] 未检测到显式唤醒或有效上下文，插件保持静默")
                return False, "未显式触发，保持静默"

            # 获取消息文本
            message_text = self.action_message.processed_plain_text.lower()
            
            # 提取标签
            raw_tags = ""
            if hasattr(self, 'action_data') and self.action_data:
                raw_tags = self.action_data.get("search_tags", "")
            
            if not raw_tags:
                raw_tags = SafebooruAPI.extract_tags(message_text)
            else:
                mapped_tags = SafebooruAPI.extract_tags(raw_tags)
                if mapped_tags:
                    raw_tags = mapped_tags
            
            search_tags = raw_tags or self.get_config("default_tags", "anime cute")
            
            # --- VBS 预校验与消歧逻辑 ---
            vbs_state = getattr(self.chat_stream, 'safebooru_vbs_state', {"count": 0, "pending_tag": None})
            vbs_results = await SafebooruAPI.validate_tags(search_tags)
            
            if vbs_results["ambiguous_entities"] and vbs_state["count"] < 3:
                ambiguous_tag = list(vbs_results["ambiguous_entities"].keys())[0]
                candidates = vbs_results["ambiguous_entities"][ambiguous_tag]
                vbs_state["count"] += 1
                vbs_state["pending_tag"] = ambiguous_tag
                self.chat_stream.safebooru_vbs_state = vbs_state
                await self._send_personality_text("检测到标签歧义，请求用户澄清", {
                    "tag": ambiguous_tag,
                    "candidates": [c['name'] for c in candidates]
                })
                return True, f"等待用户消歧: {ambiguous_tag}"

            if vbs_results["low_entropy"]:
                await self._send_personality_text("告知用户语义太弱，请求补充更多特征", {"input": search_tags})
                return True, "语义不足，已请求补充"

            final_tags = " ".join(vbs_results["validated_tags"])
            if vbs_state["count"] >= 3:
                for t, candidates in vbs_results["ambiguous_entities"].items():
                    final_tags += f" {candidates[0]['name']}"
                await self._send_personality_text("告知用户由于多次尝试未果，已自动选择最匹配的标签执行搜索", {"tags": final_tags})
            
            if hasattr(self.chat_stream, 'safebooru_vbs_state'):
                del self.chat_stream.safebooru_vbs_state

            # 1. 告知正在搜图 (完全人格化)
            await self._send_personality_text("收到搜图请求，以自然语气告知用户正在寻找相关图片", {"tags": final_tags})
            
            # 2. 搜索图片
            search_limit = max(self.get_config("max_results", 3) * 3, 10)
            rating = self.get_config("rating", "safe")
            timeout_val = self.get_config("timeout", 30)
            images = await SafebooruAPI.search_images(final_tags, search_limit, rating, timeout_val)
            
            if images:
                selected_image = random.choice(images)
                image_url = selected_image.get('file_url') or selected_image.get('sample_url')
                
                if image_url:
                    image_base64 = await SafebooruAPI.download_image(image_url)
                    if image_base64:
                        # 3. 发送图片
                        success = await self.send_image(image_base64)
                        if success:
                            # 4. 记录 Action 信息，使用强终止语约束 Planner
                            # 成功发送图片后，不再主动发送人格化描述，交由主大脑处理
                            await self.store_action_info(
                                action_build_into_prompt=True,
                                action_prompt_display=f"已成功发送关于 '{search_tags}' 的图片。任务已完成。除非用户明确要求再次搜索或更换标签，否则严禁自动重试或继续搜索相关内容。",
                                action_done=True
                            )
                            return True, f"成功发送图片: {search_tags}"
                        else:
                            await self._send_personality_text("告知图片发送失败（可能文件过大）并询问是否重试")
                    else:
                        await self._send_personality_text("告知图片下载失败并询问是否重试")
                else:
                    await self._send_personality_text("告知图片链接失效并询问是否重试")
            else:
                # 搜索失败时，不再主动发送人格化描述，交由主大脑处理
                pass
            
            # 失败或未找到时也记录信息，防止 Planner 自动重试
            await self.store_action_info(
                action_build_into_prompt=True,
                action_prompt_display=f"尝试搜索 '{search_tags}' 但未找到结果或下载失败。请告知用户结果并询问是否重试。在用户回复之前，不要进行任何自动搜索。",
                action_done=True
            )
            return True, "搜索未成功，已询问用户"
                
        except Exception as e:
            logger.error(f"[SafebooruAction] 执行错误: {e}")
            await self._send_personality_text("告知发生未知错误导致搜索中断，并询问是否重试")
            # 即使发生异常也记录 action_done，防止 Planner 陷入错误修复循环
            await self.store_action_info(
                action_build_into_prompt=True,
                action_prompt_display=f"执行过程中发生错误: {str(e)}。已告知用户并等待反馈。严禁自动重试。",
                action_done=True
            )
            return True, f"执行错误: {e}"


class SafebooruTool(BaseTool):
    """Safebooru图片搜索Tool组件 - 供LLM调用"""
    
    name = "safebooru_search"
    description = "从Safebooru搜索动漫图片，支持按标签搜索"
    parameters = [
        ("tags", ToolParamType.STRING, "搜索标签，多个标签用空格分隔", True, None),
        ("limit", ToolParamType.INTEGER, "返回结果数量限制，默认1，最大10", False, None),
        ("rating", ToolParamType.STRING, "图片等级限制: safe/questionable/explicit，默认safe", False, ["safe", "questionable", "explicit"]),
    ]
    available_for_llm = True
    
    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行Safebooru图片搜索"""
        try:
            tags = function_args.get("tags", "")
            limit = min(function_args.get("limit", 1), 10)  # 限制最大10张
            rating = function_args.get("rating", "safe")
            
            if not tags:
                return {
                    "content": f"❌ 缺少必需参数: tags",
                    "success": False
                }
            
            # --- VBS 预校验层 ---
            vbs_results = await SafebooruAPI.validate_tags(tags)
            
            if vbs_results["ambiguous_entities"]:
                ambiguous_tag = list(vbs_results["ambiguous_entities"].keys())[0]
                candidates = [c['name'] for c in vbs_results["ambiguous_entities"][ambiguous_tag]]
                return {
                    "content": f"⚠️ 标签 '{ambiguous_tag}' 存在歧义，请从以下建议中选择更具体的标签：{', '.join(candidates)}",
                    "success": False,
                    "ambiguity": vbs_results["ambiguous_entities"]
                }

            if vbs_results["low_entropy"]:
                return {
                    "content": f"⚠️ 标签 '{tags}' 语义太弱（如 girl, solo 等），请提供更具体的特征（如角色名、作品名或具体的服装描述）。",
                    "success": False
                }

            final_tags = " ".join(vbs_results["validated_tags"])
            
            # 搜索图片
            images = await SafebooruAPI.search_images(final_tags, limit, rating, 30)
            
            if not images:
                return {
                    "content": f"😔 没有找到标签为 '{tags}' 的图片呢~试试其他标签吧！",
                    "success": False
                }
            
            # 处理图片信息
            processed_images = []
            for img in images:
                processed_images.append({
                    "id": img.get("id"),
                    "file_url": img.get("file_url"),
                    "sample_url": img.get("sample_url"),
                    "preview_url": img.get("preview_url"),
                    "width": img.get("width"),
                    "height": img.get("height"),
                    "tags": img.get("tags", ""),
                    "rating": img.get("rating", "unknown"),
                    "score": img.get("score", 0)
                })
            
            # 构建返回内容
            content = f"✅ 找到 {len(processed_images)} 张关于 '{tags}' 的图片：\n\n"
            for i, img in enumerate(processed_images[:3], 1):  # 只显示前3张
                content += f"{i}. ID: {img['id']}, 评分: {img['score']}\n"
                content += f"   标签: {img['tags'][:50]}{'...' if len(img['tags']) > 50 else ''}\n\n"
            
            return {
                "content": content,
                "success": True,
                "tags": tags,
                "count": len(processed_images),
                "images": processed_images
            }
            
        except Exception as e:
            logger.error(f"[SafebooruTool] 执行错误: {e}")
            return {
                "content": f"💥 搜索过程中出现错误: {str(e)}",
                "success": False
            }


@register_plugin
class SafebooruPlugin(BasePlugin):
    """Safebooru动漫图片搜索插件"""
    
    # 插件基本信息
    plugin_name: str = "safebooru_plugin"
    enable_plugin: bool = True
    dependencies: List[str] = []  # 改为空，因为aiohttp和Pillow应该由系统管理
    python_dependencies: List[str] = []  # 改为空，避免依赖检查问题
    config_file_name: str = "config.toml"
    
    # 配置节描述
    config_section_descriptions = {
        "plugin": "插件基本信息",
        "safebooru": "Safebooru搜索配置",
        "response": "回复风格配置"
    }
    
    # 配置Schema定义
    config_schema: dict = {
        "plugin": {
            "config_version": ConfigField(type=str, default="1.0.0", description="配置文件版本"),
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件"),
        },
        "safebooru": {
            "default_tags": ConfigField(type=str, default="anime cute", description="默认搜索标签"),
            "max_results": ConfigField(type=int, default=3, description="搜索结果最大数量"),
            "rating": ConfigField(type=str, default="safe", description="图片等级限制"),
            "timeout": ConfigField(type=int, default=60, description="请求超时时间（秒）"),
        },
        "response": {
            "show_tags": ConfigField(type=bool, default=False, description="是否显示图片标签信息"),
            "personality_style": ConfigField(type=str, default="cute", description="人格风格: cute/cool/elegant"),
            "enable_natural_search": ConfigField(type=bool, default=True, description="是否启用自然语言搜索"),
        }
    }
    
    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        return [
            (SafebooruCommand.get_command_info(), SafebooruCommand),
            (SafebooruAction.get_action_info(), SafebooruAction),
            (SafebooruTool.get_tool_info(), SafebooruTool),
        ]
