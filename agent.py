import json
import os
import re
import asyncio
import base64
import time
from openai import OpenAI
from search_xhs import search_and_extract_multiple

# 加载配置文件
CONFIG_FILE = "config.json"
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
else:
    print(f"❌ 找不到配置文件 {CONFIG_FILE}！")
    exit(1)

# 初始化 OpenAI 兼容客户端
API_BASE = config.get("api_base", "http://localhost:11434/v1")
API_KEY = config.get("api_key", "ollama")
MODEL_NAME = config.get("model_name", "qwen3.5:35b")
VISION_MODEL_NAME = config.get("vision_model_name", "qwen3-vl:32b")
ENABLE_VISION = config.get("enable_vision", False)
VISION_TEXT_THRESHOLD = config.get("vision_text_threshold", 100)
SAVE_SUMMARY = config.get("save_summary_to_file", True)

# 创建 LLM 客户端
try:
    client = OpenAI(base_url=API_BASE, api_key=API_KEY)
except Exception as e:
    print(f"❌ 初始化 LLM 客户端失败: {e}")
    exit(1)

# 下载并转换图片为 Base64
import requests  # 需要在前面保留requests用于下载图片


def url_to_base64(image_url):
    try:
        print(f"      ⬇️ 正在下载笔记配图: {image_url[:50]}...")
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()
        encoded = base64.b64encode(response.content).decode("utf-8")
        return encoded
    except Exception as e:
        print(f"      ❌ 图片下载失败: {e}")
        return None


# 调用视觉大模型
def extract_text_from_image(base64_img, context_title):
    print(f"      👁️ 正在调用多模态大模型 ({VISION_MODEL_NAME}) 解析图片...")
    system_prompt = (
        "你是一个图片分析助手。请仔细观察这张图片。"
        "如果图片里有大段的干货文字（比如攻略路线、避坑提示、产品价格清单等），请把它们提取出来。"
        "如果是一张风景/产品展示图，请简短描述它的内容。"
        "不要回复其他废话，直接输出提取的文字或描述。"
    )
    try:
        # 视觉推理可能非常慢
        response = client.chat.completions.create(
            model=VISION_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"这是小红书笔记《{context_title}》的配图。",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_img}"
                            },
                        },
                    ],
                },
            ],
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"      ❌ 多模态解析失败: {e}")
        return None


def generate_search_keywords(user_prompt):
    """
    调用本地大模型，解析用户的意图，生成 1-3 个小红书搜索关键词
    """
    print(f"🧠 正在调用大模型拆解 Prompt: '{user_prompt}'")

    system_prompt = (
        "你是一个小红书搜索专家。用户的输入可能是一段复杂的需求或模糊的话。"
        "你的任务是从用户的输入中提取、拓展出 1 到 3 个适合在小红书直接搜索的高级关键词短语。\n"
        "要求：\n"
        '1. 返回的内容必须且仅仅是一个 JSON 数组（列表），例如：["西湖旅游路线", "西湖必吃美食", "杭州避坑指南"]。\n'
        "2. 不要返回任何前言、后记或其他 markdown 格式的代码块（绝对不要包含 ```json 这样的标识符），只返回中括号及中间的字符串数组。"
    )

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )

        content = response.choices[0].message.content.strip()

        # 使用正则安全提取 JSON 数组（哪怕大模型多说了一些废话也能匹配到里面的数组）
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if match:
            json_str = match.group(0)
            keywords = json.loads(json_str)
            # 限制最多 3 个
            keywords = keywords[:3]
            print(f"✅ 生成的并行搜索关键词: {keywords}")
            return keywords
        else:
            print(f"❌ 无法从模型回复中提取关键词数组: {content}")
            return [user_prompt]

    except Exception as e:
        print(f"❌ 请求大模型生成关键词失败: {e}")
        return [user_prompt]  # 如果失败退回到原 prompt 作为单一搜索词


def summarize_with_ollama(notes_data, user_prompt):
    """
    将抓取到的笔记数据发送给大模型进行总结。
    """
    if not notes_data:
        return "❌ 没有提供任何笔记数据供总结。"

    print(
        f"\n🧠 正在将 {len(notes_data)} 篇笔记提交给大模型 ({MODEL_NAME}) 进行总结..."
    )

    # 1. 组装输入给大模型的 Prompt
    context_text = ""
    for idx, note in enumerate(notes_data, 1):
        context_text += f"\n--- 笔记 {idx} ---\n"
        context_text += f"来源关键词: {note.get('keyword', '未知')}\n"
        context_text += f"标题: {note.get('title', '无标题')}\n"
        context_text += f"正文: {note.get('content', '无正文')}\n"
        context_text += f"链接: {note.get('url', '无链接')}\n"

    system_prompt = (
        "你是一个专业的小红书内容分析助手。你的任务是根据用户提供的多篇小红书笔记内容，"
        "提取核心信息，并生成一份结构清晰、客观实用的总结报告。\n"
        "总结要求：\n"
        "1. 概括主要观点或核心信息。\n"
        "2. 如果是攻略类（如旅游、购物），请列出具体的推荐（如景点、美食、产品）和避坑指南。\n"
        "3. 保持客观，不要虚构笔记中不存在的信息。\n"
        "4. 输出格式尽量使用 Markdown（如加粗、列表）。"
    )

    user_message = f"用户的原始需求是：'{user_prompt}'\n\n以下是我为你跨关键词抓取到的相关小红书笔记内容：\n{context_text}\n\n请根据上述笔记内容，为用户生成一份详细的总结报告。"

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
        )

        summary = response.choices[0].message.content
        print("✅ 总结生成完成！\n")
        return summary

    except Exception as e:
        print(f"\n❌ 连接大模型 API 失败: {e}")
        return "无法连接到大模型服务。"


# 注意：原本的 main 函数现在必须变成异步，以便调用 asyncio.run(search_...)
async def main_async():
    print("=" * 50)
    print("🍠 欢迎使用 Sweet Potato Lens (小红薯透镜 Agent)")
    print("=" * 50)

    # 获取默认配置
    default_prompt = config.get("default_prompt", "西湖一日游必去景点与美食")
    breakpoint
    default_num_notes = config.get("num_notes_to_fetch", 3)

    user_prompt = input(
        f"\n👉 请输入你想在小红书搜索的内容 (直接按回车使用默认值: '{default_prompt}'): "
    ).strip()

    if not user_prompt:
        user_prompt = default_prompt

    if user_prompt.lower() == "q":
        print("👋 感谢使用，再见！")
        return

    try:
        num_str = input(
            f"👉 请输入【每个关键词】要抓取前几篇笔记 (直接按回车使用配置值: {default_num_notes}): "
        ).strip()
        num_notes = int(num_str) if num_str else default_num_notes
    except ValueError:
        print(f"输入无效，默认使用配置值: {default_num_notes}。")
        num_notes = default_num_notes

    print("\n" + "-" * 30)

    # 步骤 1: 让大模型解析 prompt，生成并行搜索的关键词
    keywords = generate_search_keywords(user_prompt)

    if not keywords:
        print("⚠️ 未能生成搜索关键词。")
        return

    print("\n" + "-" * 30)

    # 步骤 2: 并行调度爬虫（异步执行）
    notes_data = await search_and_extract_multiple(keywords, num_notes=num_notes)

    if not notes_data:
        print("\n⚠️ 未能抓取到任何笔记数据，Agent 流程终止。")
        return

    print("\n" + "-" * 30)

    # 步骤 2.5: (可选的多模态增强) 如果开启且正文过少，自动触发 Qwen-VL 看图
    if ENABLE_VISION:
        print(f"👁️ 多模态已开启 ({VISION_MODEL_NAME})。正在智能筛选需要看图的笔记...")
        vision_count = 0
        for note in notes_data:
            # 判断逻辑：如果内容字数低于阈值（很可能是看图说话的笔记），并且抓到了首图链接
            if (
                note.get("image_url")
                and len(note.get("content", "")) < VISION_TEXT_THRESHOLD
            ):
                print(
                    f"  > 发现低信息量笔记: 《{note['title']}》(正文仅 {len(note.get('content', ''))} 字，低于阈值 {VISION_TEXT_THRESHOLD})，准备启动视觉增强"
                )
                base64_img = url_to_base64(note["image_url"])
                if base64_img:
                    vision_text = extract_text_from_image(base64_img, note["title"])
                    if vision_text:
                        print(
                            f"      ✅ 视觉提取成功，新增 {len(vision_text)} 字信息补充到正文中！"
                        )
                        note["content"] += (
                            f"\n\n[ Sweet Potato Lens 🍠 视觉识别提取的干货 ]: \n{vision_text}"
                        )
                        vision_count += 1
        if vision_count > 0:
            print(f"✨ 视觉增强完成！共解析了 {vision_count} 张干货图片。")
        else:
            print("👌 本次搜索的笔记正文内容丰富，未触发视觉增强。")
    else:
        print("⏭️ 多模态视觉提取已关闭 (在 config.json 中修改 enable_vision 可开启)。")

    print("\n" + "-" * 30)

    # 步骤 3: 汇总总结
    summary = summarize_with_ollama(notes_data, user_prompt)

    print("✨ --- 最终总结报告 --- ✨\n")
    print(summary)
    print("\n" + "=" * 50)

    # 步骤 4: 自动保存总结文件
    if SAVE_SUMMARY:
        # 清理文件名中的非法字符
        safe_prompt = re.sub(r'[\\/*?:"<>|]', "", user_prompt)[:20]
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"SweetPotatoLens_报告_{safe_prompt}_{timestamp}.md"

        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"# 🍠 Sweet Potato Lens 探索报告: {user_prompt}\n\n")
                f.write(f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(summary)
            print(f"📄 总结已自动保存至本地文件：【{filename}】")
        except Exception as e:
            print(f"❌ 保存文件失败: {e}")


def run_xhs_agent():
    # 入口点：运行异步主循环
    asyncio.run(main_async())


if __name__ == "__main__":
    run_xhs_agent()
