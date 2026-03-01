import os
from playwright.sync_api import sync_playwright

# 获取当前脚本所在目录的绝对路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 保存登录状态的文件路径
STATE_FILE = os.path.join(BASE_DIR, "xhs_state.json")


def login_and_save_state():
    print("正在启动 Playwright 浏览器...")
    with sync_playwright() as p:
        # headless=False 表示显示浏览器界面，这样你才能扫码
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print("正在访问小红书网页版...")
        page.goto("https://www.xiaohongshu.com")

        print("\n" + "=" * 50)
        print("请在弹出的浏览器中手动登录（推荐使用手机APP扫码登录）。")
        print("登录成功，并且页面已经完全加载出你的首页推荐后，")
        print("请回到这个命令行窗口，按下【回车键】(Enter) 继续...")
        print("=" * 50 + "\n")

        # 程序会在这里暂停，等待你按下回车
        input("【等待操作】完成登录后，请按回车键以保存登录状态：")

        # 将当前浏览器的 Cookies 和 LocalStorage 保存到本地 JSON 文件中
        context.storage_state(path=STATE_FILE)
        print(f"\n✅ 登录状态已成功保存到当前目录的 {STATE_FILE} 文件中！")
        print("接下来我们的 Agent 就可以拿着这个文件‘免密’自动操作了。")

        browser.close()


if __name__ == "__main__":
    login_and_save_state()
