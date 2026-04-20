from __future__ import annotations

import sys

# top level


def main() -> int:
    if len(sys.argv) > 1:
        cmd = sys.argv[1]

    try:
        from .bootstrap import bootstrap_platform_services

        platform_services = bootstrap_platform_services()

        from .app_kernel import AppKernel

        kernel = AppKernel(platform_services=platform_services)
        kernel.run()
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        import traceback
        import tkinter as tk
        from tkinter import messagebox
        
        error_msg = traceback.format_exc()
        print(f"deskvane crash:\n{error_msg}", file=sys.stderr)
        
        try:
            root = tk.Tk()
            root.title("DeskVane 启动失败 (致命错误)")
            w, h = 600, 400
            root.geometry(f"{w}x{h}+{(root.winfo_screenwidth()-w)//2}+{(root.winfo_screenheight()-h)//2}")
            
            tk.Label(root, text="DeskVane 在启动时遇到了严重错误：", fg="red", font=("sans-serif", 11, "bold")).pack(pady=10)
            
            frame = tk.Frame(root)
            frame.pack(fill=tk.BOTH, expand=True, padx=15)
            
            txt = tk.Text(frame, wrap=tk.NONE, font=("Consolas", 10), bg="#f5f5f5")
            txt.insert(tk.END, error_msg)
            txt.config(state=tk.DISABLED)
            
            scrolly = tk.Scrollbar(frame, command=txt.yview)
            scrollx = tk.Scrollbar(frame, orient=tk.HORIZONTAL, command=txt.xview)
            txt.config(yscrollcommand=scrolly.set, xscrollcommand=scrollx.set)
            
            scrolly.pack(side=tk.RIGHT, fill=tk.Y)
            scrollx.pack(side=tk.BOTTOM, fill=tk.X)
            txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            def copy_error():
                root.clipboard_clear()
                root.clipboard_append(error_msg)
                
            btn_frame = tk.Frame(root)
            btn_frame.pack(pady=15)
            tk.Button(btn_frame, text="复制错误并关闭", command=lambda: [copy_error(), root.destroy()]).pack(side=tk.LEFT, padx=10)
            tk.Button(btn_frame, text="仅关闭", command=root.destroy).pack(side=tk.LEFT)
            
            root.mainloop()
        except Exception:
            pass
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
