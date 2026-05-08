import pathlib

from ..config import CONFIG_DIR, AppConfig

def generate_help_html(cfg: AppConfig) -> pathlib.Path:
    def esc(value: object) -> str:
        text = str(value)
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="utf-8">
        <title>DeskVane 帮助</title>
        <style>
            :root {{
                color-scheme: light;
                --bg: #f5f6fa;
                --panel: #ffffff;
                --border: #dde1e8;
                --text: #1b2230;
                --muted: #667085;
                --accent: #0a84ff;
            }}
            body {{
                margin: 0;
                background: var(--bg);
                color: var(--text);
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Microsoft YaHei", sans-serif;
                line-height: 1.6;
            }}
            .page {{
                max-width: 860px;
                margin: 0 auto;
                padding: 40px 24px 48px;
            }}
            .header {{
                margin-bottom: 24px;
            }}
            h1 {{
                margin: 0 0 8px;
                font-size: 28px;
                font-weight: 600;
                letter-spacing: -0.02em;
            }}
            .lead {{
                margin: 0;
                color: var(--muted);
                font-size: 15px;
            }}
            .card {{
                background: var(--panel);
                border: 1px solid var(--border);
                border-radius: 16px;
                padding: 20px 22px;
                margin-bottom: 16px;
                box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
            }}
            h2 {{
                margin: 0 0 8px;
                font-size: 17px;
                font-weight: 600;
            }}
            p {{
                margin: 0 0 12px;
                color: var(--text);
            }}
            ul {{
                margin: 0;
                padding-left: 1.25rem;
            }}
            li {{
                margin-bottom: 8px;
            }}
            kbd {{
                display: inline-block;
                padding: 0.12rem 0.45rem;
                border: 1px solid var(--border);
                border-bottom-color: #cfd5df;
                border-radius: 6px;
                background: #fafbfc;
                font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
                font-size: 0.86em;
            }}
            code {{
                background: #f6f8fb;
                border: 1px solid #e6eaf0;
                border-radius: 6px;
                padding: 0.14rem 0.38rem;
                font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
                word-break: break-all;
            }}
            .muted {{
                color: var(--muted);
            }}
            .footer {{
                margin-top: 24px;
                color: var(--muted);
                font-size: 13px;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <div class="page">
            <div class="header">
                <h1>DeskVane 帮助</h1>
                <p class="lead">按快捷键或通过托盘菜单使用常用功能。帮助页只列出最常见的入口和配置位置。</p>
            </div>

            <div class="card">
                <h2>翻译和 OCR</h2>
                <p>这些功能通过快捷键触发，也可从托盘菜单打开。</p>
                <ul>
                    <li><strong>划词翻译</strong>：选中文本后复制，系统会在鼠标附近显示结果。</li>
                    <li><strong>暂停或恢复监控</strong>：按下 <kbd>{esc(getattr(cfg.translator, "hotkey_toggle_pause", "<ctrl>+<alt>+t"))}</kbd>。</li>
                    <li><strong>纯 OCR</strong>：按下 <kbd>{esc(getattr(cfg.screenshot, "hotkey_pure_ocr", "<alt>+<f1>"))}</kbd> 后框选区域。</li>
                </ul>
            </div>

            <div class="card">
                <h2>截图和钉图</h2>
                <p>截图支持保存、复制和钉在屏幕上。</p>
                <ul>
                    <li><strong>普通截图</strong>：按下 <kbd>{esc(getattr(cfg.screenshot, "hotkey", "<ctrl>+<f1>"))}</kbd>。</li>
                    <li><strong>钉图截图</strong>：按下 <kbd>{esc(getattr(cfg.screenshot, "hotkey_pin", "<ctrl>+<f2>"))}</kbd>。</li>
                    <li><strong>关闭悬浮图片</strong>：双击图片即可关闭。</li>
                </ul>
            </div>

            <div class="card">
                <h2>剪贴板历史</h2>
                <p>记录最近复制过的文本，方便快速回填。</p>
                <ul>
                    <li>按下 <kbd>{esc(getattr(cfg.general, "hotkey_clipboard_history", "<alt>+v"))}</kbd> 打开历史面板。</li>
                    <li>使用方向键或数字键选择条目，按 <kbd>Enter</kbd> 确认。</li>
                    <li>按 <kbd>Esc</kbd> 可取消。</li>
                </ul>
            </div>

            <div class="card">
                <h2>代理</h2>
                <p>Git 和终端可以共用同一组代理设置。</p>
                <ul>
                    <li>在托盘菜单中打开代理开关。</li>
                    <li>新开终端会读取当前代理环境变量。</li>
                </ul>
            </div>

            <div class="card">
                <h2>订阅转换</h2>
                <p>本地订阅转换工具，把机场订阅转成 YAML 配置，再导入你常用的 Clash/Mihomo 客户端。</p>
                <ul>
                    <li><strong>订阅转换</strong>：在转换窗口输入订阅地址或原始链接。</li>
                    <li><strong>导出</strong>：转换结果可直接复制或保存为 YAML 文件。</li>
                </ul>
            </div>

            <div class="card">
                <h2>常用路径</h2>
                <ul>
                    <li>配置文件：<code>{esc(CONFIG_DIR)}/config.yaml</code></li>
                    <li>帮助页面：<code>{esc(CONFIG_DIR)}/help.html</code></li>
                </ul>
            </div>

            <p class="footer">DeskVane</p>
        </div>
    </body>
    </html>
    """
    path = CONFIG_DIR / "help.html"
    try:
        path.write_text(html_content, encoding="utf-8")
    except Exception:
        pass
    return path
