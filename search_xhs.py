import asyncio
from playwright.async_api import async_playwright
import json
import os
import sys

# 获取当前脚本所在目录的绝对路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 登录状态和配置文件绝对路径
STATE_FILE = os.path.join(BASE_DIR, "xhs_state.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")


def safe_print(text):
    """
    在 Windows 下安全地打印包含 Emoji 的文本。
    如果遇到编码错误（如 GBK 终端），则尝试忽略无法编码的字符。
    对于 MCP 服务，这能有效防止服务因为打印 Emoji 而崩溃。
    """
    try:
        print(text)
    except UnicodeEncodeError:
        try:
            print(text.encode("gbk", "ignore").decode("gbk"))
        except Exception:
            pass  # 极端情况下直接静音，不影响主流程


def get_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


async def fetch_note(context, link, keyword):
    """
    并行提取单篇笔记的内容（在一个新标签页中）
    """
    page = await context.new_page()
    try:
        # domcontentloaded 比 networkidle 快，只要骨架出来就行
        await page.goto(link, wait_until="domcontentloaded")

        title = "未找到标题"
        try:
            title_element = await page.wait_for_selector("#detail-title", timeout=3000)
            if title_element:
                title = await title_element.inner_text()
        except Exception:
            pass

        content = "未找到正文"
        try:
            content_element = await page.wait_for_selector("#detail-desc", timeout=3000)
            if content_element:
                content = await content_element.inner_text()
        except Exception:
            pass

        # 新增：尝试提取笔记的第一张大图链接
        image_url = None
        try:
            # 小红书图片通常在这个类名下，找第一张 img 标签
            img_element = await page.wait_for_selector(
                ".swiper-slide-active img, .note-scroller img", timeout=2000
            )
            if img_element:
                image_url = await img_element.get_attribute("src")
                # 如果是带水印的或者其他格式，尽量取高清原图的链接（通常不用处理，直接用 src 即可）
        except Exception:
            pass

        safe_print(f"    📝 [关键词: {keyword}] 成功抓取: {title[:15]}...")
        return {
            "keyword": keyword,
            "url": link,
            "title": title.strip(),
            "content": content.strip(),
            "image_url": image_url,  # 加入字典返回
        }
    except Exception as e:
        safe_print(f"    ❌ 抓取单篇笔记失败: {link} - {e}")
        return None
    finally:
        await page.close()  # 必须关闭，释放内存


async def search_keyword(context, keyword, num_notes):
    """
    并行搜索单个关键词，获取笔记链接并调度并行抓取任务
    """
    page = await context.new_page()
    try:
        search_url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}&source=web_search_result_notes"
        safe_print(f"🔍 正在搜索关键词: '{keyword}'...")
        await page.goto(search_url, wait_until="domcontentloaded")

        # 等待搜索结果出现
        await page.wait_for_selector("section.note-item", timeout=10000)

        note_links = []
        note_elements = await page.query_selector_all("section.note-item a.cover")

        for element in note_elements[:num_notes]:
            href = await element.get_attribute("href")
            if href:
                full_url = (
                    f"https://www.xiaohongshu.com{href}"
                    if href.startswith("/")
                    else href
                )
                note_links.append(full_url)

        safe_print(
            f"🔗 [关键词: {keyword}] 找到 {len(note_links)} 篇笔记链接，开始并行抓取..."
        )

        # 并行发起该关键词下所有笔记的抓取请求 (打开多个新标签页)
        tasks = [fetch_note(context, link, keyword) for link in note_links]
        results = await asyncio.gather(*tasks)

        # 过滤掉抓取失败的 None 结果
        return [r for r in results if r is not None]

    except Exception as e:
        safe_print(f"❌ 搜索或页面加载失败 ({keyword}): {e}")
        return []
    finally:
        await page.close()


async def search_and_extract_multiple(keywords, num_notes=3):
    """
    接收一个关键词列表，并行启动多个关键词搜索
    """
    config = get_config()
    is_headless = config.get("headless_browser", True)

    if not os.path.exists(STATE_FILE):
        safe_print(
            f"❌ 找不到登录状态文件 {STATE_FILE}，请先运行 login_xhs.py 进行登录！"
        )
        return None

    safe_print(f"\n🚀 启动浏览器，将开启 {len(keywords)} 个搜索任务...\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=is_headless)
        context = await browser.new_context(storage_state=STATE_FILE)

        # 调度所有的关键词搜索任务并行执行 (打开多个搜索标签页)
        tasks = [search_keyword(context, kw, num_notes) for kw in keywords]

        # gather 会等待所有任务完成并返回结果列表（每个元素是一个关键词的结果列表）
        all_keyword_results = await asyncio.gather(*tasks)

        # 展平结果：将 [[笔记1, 笔记2], [笔记3]] 变成 [笔记1, 笔记2, 笔记3]
        flat_results = []
        for res_list in all_keyword_results:
            flat_results.extend(res_list)

        # 根据 URL 去重 (以防不同关键词搜出同一篇笔记)
        unique_results = []
        seen_urls = set()
        for note in flat_results:
            if note["url"] not in seen_urls:
                unique_results.append(note)
                seen_urls.add(note["url"])

        await browser.close()

    safe_print(f"\n🎉 抓取完成！共收集并去重得到 {len(unique_results)} 篇笔记。")
    return unique_results
