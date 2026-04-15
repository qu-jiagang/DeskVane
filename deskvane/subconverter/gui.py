import yaml
import tkinter as tk
import tkinter.messagebox as messagebox
from tkinter import filedialog
from typing import TYPE_CHECKING

from .service import convert_subscription_source_to_yaml
from ..ui_theme import (
    ACCENT,
    ACCENT_FG,
    BG,
    BORDER,
    CARD,
    CARD_ALT,
    SUBTEXT,
    TEXT,
    button as themed_button,
    card as themed_card,
    make_font,
)

if TYPE_CHECKING:
    from ..app import DeskVaneApp


class SubconverterDialog:
    def __init__(self, app: "DeskVaneApp") -> None:
        self.app = app
        self.top = tk.Toplevel(app.root)
        self.top.title("订阅转换")
        self.top.geometry("920x680")
        self.top.minsize(800, 580)
        self.top.configure(bg=BG, padx=20, pady=20)
        self.top.protocol("WM_DELETE_WINDOW", self.top.destroy)
        self._output_visible = False

        self.top.update_idletasks()
        w, h = 920, 680
        sw = self.top.winfo_screenwidth()
        sh = self.top.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.top.geometry(f"{w}x{h}+{x}+{y}")

        header = tk.Frame(self.top, bg=BG)
        header.pack(fill=tk.X, pady=(0, 14))
        tk.Label(
            header,
            text="订阅转换",
            bg=BG,
            fg=TEXT,
            font=make_font(18, weight="bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="把订阅链接转换成 YAML，需要时再写入本地 Core。",
            bg=BG,
            fg=SUBTEXT,
            font=make_font(11),
        ).pack(anchor="w", pady=(4, 0))

        input_card = themed_card(self.top, fill=tk.X, pady=(0, 12))
        input_body = tk.Frame(input_card, bg=CARD)
        input_body.pack(fill=tk.X, padx=16, pady=16)
        tk.Label(
            input_body,
            text="输入",
            bg=CARD,
            fg=TEXT,
            font=make_font(12, weight="bold"),
        ).pack(anchor="w")
        tk.Label(
            input_body,
            text="支持订阅链接、Base64 或裸节点。",
            bg=CARD,
            fg=SUBTEXT,
            font=make_font(11),
        ).pack(anchor="w", pady=(4, 10))

        input_box = tk.Frame(input_body, bg=CARD)
        input_box.pack(fill=tk.X)
        input_box.grid_columnconfigure(0, weight=1)
        input_box.grid_rowconfigure(0, weight=1)
        self.text_in = tk.Text(
            input_box,
            height=7,
            bg=CARD_ALT,
            fg=TEXT,
            insertbackground=TEXT,
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            font=make_font(11, mono=True),
            wrap=tk.WORD,
        )
        input_scroll_y = tk.Scrollbar(input_box, orient="vertical", command=self.text_in.yview)
        self.text_in.configure(yscrollcommand=input_scroll_y.set)
        self.text_in.grid(row=0, column=0, sticky="nsew")
        input_scroll_y.grid(row=0, column=1, sticky="ns")

        actions = tk.Frame(self.top, bg=BG)
        actions.pack(fill=tk.X, pady=(0, 12))
        themed_button(
            actions,
            text="转换",
            command=self._convert,
            variant="primary",
            compact=True,
            font=make_font(10, weight="bold"),
        ).pack(side=tk.LEFT, padx=(0, 10))
        themed_button(
            actions,
            text="写入 Core",
            command=self._apply_to_core,
            variant="secondary",
            compact=True,
        ).pack(side=tk.LEFT, padx=(0, 10))
        self._toggle_output_btn = themed_button(
            actions,
            text="显示结果",
            command=self._toggle_output_panel,
            variant="ghost",
            compact=True,
        )
        self._toggle_output_btn.pack(side=tk.LEFT)

        self.output_wrap = tk.Frame(self.top, bg=BG)
        output_card = themed_card(self.output_wrap, fill=tk.BOTH, expand=True, pady=(0, 12))
        output_body = tk.Frame(output_card, bg=CARD)
        output_body.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        tk.Label(
            output_body,
            text="结果",
            bg=CARD,
            fg=TEXT,
            font=make_font(12, weight="bold"),
        ).pack(anchor="w")
        tk.Label(
            output_body,
            text="默认折叠。需要时再查看、复制或导出。",
            bg=CARD,
            fg=SUBTEXT,
            font=make_font(11),
        ).pack(anchor="w", pady=(4, 10))

        output_box = tk.Frame(output_body, bg=CARD)
        output_box.pack(fill=tk.BOTH, expand=True)
        output_box.grid_columnconfigure(0, weight=1)
        output_box.grid_rowconfigure(0, weight=1)
        self.text_out = tk.Text(
            output_box,
            bg=CARD_ALT,
            fg=TEXT,
            insertbackground=TEXT,
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            font=make_font(11, mono=True),
            wrap=tk.NONE,
        )
        output_scroll_y = tk.Scrollbar(output_box, orient="vertical", command=self.text_out.yview)
        output_scroll_x = tk.Scrollbar(output_box, orient="horizontal", command=self.text_out.xview)
        self.text_out.configure(
            yscrollcommand=output_scroll_y.set,
            xscrollcommand=output_scroll_x.set,
        )
        self.text_out.grid(row=0, column=0, sticky="nsew")
        output_scroll_y.grid(row=0, column=1, sticky="ns")
        output_scroll_x.grid(row=1, column=0, sticky="ew")

        btn_frame = tk.Frame(output_body, bg=CARD)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        themed_button(btn_frame, "复制", self._copy, variant="secondary", compact=True).pack(side=tk.LEFT, padx=(0, 10))
        themed_button(btn_frame, "导出", self._save, variant="ghost", compact=True).pack(side=tk.LEFT)

        self._set_output_visible(False)
        self._activate_input()

    def _activate_input(self) -> None:
        try:
            self.top.lift()
            self.top.focus_force()
        except tk.TclError:
            pass

        def _focus_input() -> None:
            try:
                self.top.lift()
                self.top.focus_force()
                self.text_in.focus_set()
                self.text_in.mark_set(tk.INSERT, "1.0")
                self.text_in.see(tk.INSERT)
            except tk.TclError:
                pass

        self.top.after(30, _focus_input)
        self.top.after(120, _focus_input)

    def _set_output_visible(self, visible: bool) -> None:
        self._output_visible = visible
        if visible:
            self.output_wrap.pack(fill=tk.BOTH, expand=True)
            self._toggle_output_btn.configure(text="隐藏结果")
        else:
            self.output_wrap.pack_forget()
            self._toggle_output_btn.configure(text="显示结果")

    def _toggle_output_panel(self) -> None:
        self._set_output_visible(not self._output_visible)

    def _convert(self) -> None:
        content = self.text_in.get("1.0", tk.END).strip()
        if not content:
            return

        try:
            yaml_str = convert_subscription_source_to_yaml(content, timeout_s=10)
            self.text_out.delete("1.0", tk.END)
            self.text_out.insert("1.0", yaml_str)
            self._set_output_visible(True)
        except Exception as e:
            messagebox.showerror("发生错误", f"转换过程中发生错误: {e}", parent=self.top)

    def _copy(self) -> None:
        content = self.text_out.get("1.0", tk.END).strip()
        if content:
            self.top.clipboard_clear()
            self.top.clipboard_append(content)
            messagebox.showinfo("已复制", "YAML 已复制到剪贴板。", parent=self.top)

    def _save(self) -> None:
        content = self.text_out.get("1.0", tk.END).strip()
        if not content:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".yaml",
            filetypes=[("YAML Config", "*.yaml"), ("All Files", "*.*")],
            title="保存 Clash 配置文件",
            parent=self.top,
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                messagebox.showinfo("保存成功", f"已保存到:\n{path}", parent=self.top)
            except Exception as e:
                messagebox.showerror("保存失败", str(e), parent=self.top)

    def _apply_to_core(self) -> None:
        content = self.text_out.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("提示", "没有可应用的配置内容！", parent=self.top)
            return

        try:
            payload = yaml.safe_load(content) or {}
            if not isinstance(payload, dict):
                raise ValueError("转换结果不是合法的 YAML 映射。")
            proxies = payload.get("proxies")
            if not isinstance(proxies, list) or not proxies:
                raise ValueError("转换结果里没有可应用的代理节点。")

            source_hint = self.text_in.get("1.0", tk.END).strip()
            if "\n" in source_hint:
                source_hint = "manual://subconverter"
            provider_path = self.app.mihomo_manager.save_subscription_provider(proxies, source_hint)
            reloaded = self.app.mihomo_manager.reload_core_config()

            if reloaded:
                body = (
                    f"Provider 已写入:\n{provider_path}\n\n"
                    "Core 正在运行，已重载。"
                )
            else:
                body = (
                    f"Provider 已写入:\n{provider_path}\n\n"
                    "Core 未运行，稍后可手动重载。"
                )
            messagebox.showinfo("保存成功", body, parent=self.top)
        except Exception as e:
            messagebox.showerror("保存失败", str(e), parent=self.top)
