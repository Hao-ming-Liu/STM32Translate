"""Compact Windows popup. All Tk and SQLite operations stay on the UI thread."""
from __future__ import annotations
from pathlib import Path
import queue
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import webbrowser
from urllib.parse import urlencode

from stm32translate import native
from stm32translate.controller import RequestState, WorkerClient
from stm32translate.resources import app_root, data_directory, CACHE_NAMESPACE, make_icon
from stm32translate.store import Store


class App:
    def __init__(self, root: tk.Tk, data_dir: Path):
        self.root, self.data_dir = root, Path(data_dir)
        root.withdraw()
        root.title('STM32 译窗')
        root.minsize(320, 240)
        root.configure(background='#f6f8fb')
        self.store = Store(self.data_dir / 'translator.db')
        self.store.seed_defaults()
        self.events = queue.Queue()
        self.client = WorkerClient(app_root() / 'models/en_zh', self.events)
        self.state = RequestState()
        self.last_translation = ''
        self.pinned = False
        self.hotkey = self.tray = self.guard = None
        self.closed = False
        self.source_visible = True
        self.shortcut = self.store.get_setting('hotkey', 'Ctrl+Alt+T')
        self.status = tk.StringVar(value=f'复制英文后按 {self.shortcut}')
        areas = native.working_areas()
        area = next((r for r in areas if r[0] <= 0 < r[2]), areas[0])
        default = [area[2]-444, area[3]-364, 420, 320]
        saved = self.store.get_setting('geometry', default)
        if not isinstance(saved, list) or len(saved) != 4 or any(not isinstance(v, int) for v in saved):
            saved = default
        self.geometry_state = native.clamp_geometry(saved[0], saved[1], max(320, saved[2]), max(240, saved[3]), areas)
        self._build()
        root.protocol('WM_DELETE_WINDOW', self.hide)
        root.bind('<Escape>', lambda _: self.hide())
        root.bind('<Control-Return>', lambda _: self.translate())
        root.bind('<Control-v>', self.paste)
        root.bind('<Control-V>', self.paste)
        self.source.bind('<<Paste>>', self.paste)
        root.bind('<FocusOut>', lambda _: root.after(180, self.check_focus))
        root.bind('<Configure>', self._on_configure)
        self._save_job = None
        self._poll_job = root.after(75, self.poll)

    def _build(self):
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('TFrame', background='#f6f8fb')
        style.configure('TLabel', background='#f6f8fb', foreground='#334155', font=('Microsoft YaHei UI', 9))
        style.configure('TButton', font=('Microsoft YaHei UI', 9), padding=(7, 4), background='#f6f8fb', borderwidth=0)
        style.map('TButton', background=[('active', '#e2e8f0')])
        style.configure('Accent.TButton', foreground='white', background='#2563eb')
        style.map('Accent.TButton', background=[('active', '#1d4ed8')])
        style.configure('Small.TLabel', foreground='#64748b', font=('Microsoft YaHei UI', 8))
        outer = ttk.Frame(self.root, padding=(12, 8, 12, 8))
        outer.pack(fill='both', expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)
        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky='ew', pady=(0, 7))
        ttk.Label(header, text='英 → 中', foreground='#0f172a', font=('Microsoft YaHei UI', 11, 'bold')).pack(side='left')
        ttk.Label(header, text='  离线', foreground='#15803d', font=('Microsoft YaHei UI', 8)).pack(side='left')
        menu_button = ttk.Menubutton(header, text='设置', width=4)
        menu = tk.Menu(menu_button, tearoff=False)
        menu.add_command(label='修改快捷键', command=self.hotkey_dialog)
        menu.add_command(label='打开数据目录', command=self.open_data_directory)
        menu.add_separator()
        menu.add_command(label='退出程序', command=self.quit)
        menu_button['menu'] = menu
        menu_button.pack(side='right')
        self.source_button = ttk.Button(header, text='收起原文', command=self.toggle_source, width=7)
        self.source_button.pack(side='right', padx=(0, 5))
        self.source_frame = ttk.Frame(outer)
        self.source_frame.grid(row=1, column=0, sticky='ew', pady=(0, 8))
        self.source_frame.columnconfigure(0, weight=1)
        self.source = tk.Text(self.source_frame, height=3, width=25, wrap='word', undo=True,
                              font=('Consolas', 10), background='white', foreground='#475569',
                              relief='flat', highlightthickness=1, highlightbackground='#dbe2ea', padx=7, pady=5)
        self.source.grid(row=0, column=0, sticky='ew')
        ttk.Button(self.source_frame, text='翻译', command=self.translate, style='Accent.TButton', width=5).grid(row=0, column=1, sticky='ns', padx=(6, 0))
        result_frame = ttk.Frame(outer)
        result_frame.grid(row=2, column=0, sticky='nsew')
        result_frame.rowconfigure(0, weight=1)
        result_frame.columnconfigure(0, weight=1)
        self.output = tk.Text(result_frame, wrap='word', width=20, height=4, state='disabled',
                              font=('Microsoft YaHei UI', 11), foreground='#172033', background='white',
                              relief='flat', highlightthickness=1, highlightbackground='#e2e8f0',
                              padx=10, pady=8, spacing1=2, spacing3=4, cursor='xterm')
        self.output.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(result_frame, orient='vertical', command=self.output.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        self.output['yscrollcommand'] = scroll.set
        self.output.tag_configure('muted', foreground='#64748b', font=('Microsoft YaHei UI', 9))
        self.output.tag_configure('terms', foreground='#166534', font=('Microsoft YaHei UI', 9))
        self.output.tag_configure('warning', foreground='#a16207', font=('Microsoft YaHei UI', 9))
        self._write('粘贴英文注释，快速读懂参数说明。\n\nCtrl+Enter 翻译 · Esc 收起', 'muted')
        actions = ttk.Frame(outer)
        actions.grid(row=3, column=0, sticky='ew', pady=(7, 3))
        self.pin_button = ttk.Button(actions, text='固定', command=self.toggle_pin, width=4)
        self.pin_button.pack(side='left')
        ttk.Button(actions, text='复制译文', command=self.copy_translation, width=7).pack(side='left', padx=(2, 0))
        ttk.Button(actions, text='联网查词', command=self.lookup, width=7).pack(side='left', padx=(2, 0))
        ttk.Button(actions, text='保存术语', command=self.term_dialog, width=7).pack(side='right')
        ttk.Label(outer, textvariable=self.status, style='Small.TLabel', anchor='w').grid(row=4, column=0, sticky='ew')

    def _write(self, text: str, tag=None, append=False):
        self.output.configure(state='normal')
        if not append:
            self.output.delete('1.0', 'end')
        self.output.insert('end', text, tag or ())
        self.output.configure(state='disabled')

    def get_source(self):
        return self.source.get('1.0', 'end-1c')

    def set_source(self, text):
        self.source.delete('1.0', 'end')
        self.source.insert('1.0', text)

    def toggle_source(self, visible=None):
        self.source_visible = not self.source_visible if visible is None else visible
        if self.source_visible:
            self.source_frame.grid()
            self.source_button.configure(text='收起原文')
        else:
            self.source_frame.grid_remove()
            self.source_button.configure(text='展开原文')

    def show(self):
        target = native.clamp_geometry(*self.geometry_state, native.working_areas())
        x, y, width, height = target
        self.root.geometry(f'{width}x{height}')
        self.root.deiconify()
        self.root.update_idletasks()
        native.place_window(self.root, x, y)
        self.root.lift()
        native.foreground(self.root)
        self.root.focus_force()
        self.geometry_state = target

    def _save_geometry(self):
        self._save_job = None
        if self.closed:
            return
        try:
            self.store.set_setting('geometry', list(self.geometry_state))
        except Exception:
            self.status.set('窗口位置未能保存，请检查数据目录是否可写。')

    def _on_configure(self, event):
        if event.widget is self.root and self.root.state() == 'normal':
            self.geometry_state = (self.root.winfo_x(), self.root.winfo_y(), self.root.winfo_width(), self.root.winfo_height())
            if self._save_job:
                self.root.after_cancel(self._save_job)
            self._save_job = self.root.after(600, self._save_geometry)

    def hide(self):
        if not self.closed:
            self._save_geometry()
            self.root.withdraw()

    def check_focus(self):
        if not self.closed and not self.pinned and self.root.state() == 'normal' and self.root.grab_current() is None and not native.own_foreground():
            self.hide()

    def toggle_pin(self):
        self.pinned = not self.pinned
        self.root.attributes('-topmost', self.pinned)
        self.pin_button.configure(text='取消固定' if self.pinned else '固定', width=7 if self.pinned else 4)

    def from_clipboard(self):
        self.show()
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            self.status.set('剪贴板没有可翻译的文字，请复制英文后重试。')
            return
        if not text.strip():
            self.status.set('剪贴板为空，请先复制英文。')
            return
        self.set_source(text)
        self.translate()

    def paste(self, event=None):
        self.from_clipboard()
        return 'break'

    def translate(self):
        text = self.get_source().strip()
        request_id = self.state.begin(text)
        if not text:
            self.status.set('请先粘贴英文注释。')
            return
        if len(text) > 30000:
            self.status.set('输入超过 30000 字符，请拆分后翻译。')
            return
        term = self.store.exact_term(text)
        if term:
            self.render(term['meaning'], [], '本地术语 · 无需加载模型')
            return
        cached = self.store.cache_get(text, CACHE_NAMESPACE)
        if cached:
            self.render(cached['text'], cached['warnings'], '本地缓存')
            return
        self.last_translation = ''
        self._write('正在离线翻译…\n首次查询需要加载模型。', 'muted')
        self.status.set('翻译中，可继续复制下一段…')
        self.client.submit(request_id, text)

    def render(self, text, warnings, status):
        self.last_translation = text
        self._write(text)
        terms = self.store.match_terms(self.state.source)
        if terms:
            self._write('\n\n已存术语\n' + '\n'.join(t['term'] + '：' + t['meaning'] for t in terms), 'terms', append=True)
        if warnings:
            self._write('\n\n原文保留提示\n' + '\n'.join(warnings), 'warning', append=True)
            status += f' · {len(warnings)} 个片段保留原文'
        self.status.set(status)
        self.toggle_source(False)

    def handle_result(self, result):
        if not self.state.accept(result.get('id')) or self.get_source().strip() != self.state.source:
            return
        if result.get('error'):
            self.last_translation = ''
            self._write(result['error'], 'warning')
            self.status.set('翻译未完成，可以重试。')
            return
        try:
            self.store.cache_put(self.state.source, CACHE_NAMESPACE, result['text'], result.get('warnings', []))
        except Exception:
            self.status.set('译文已生成，缓存未能写入。')
        self.render(result['text'], result.get('warnings', []), f"离线完成 · {result.get('elapsed', 0):.1f} 秒")

    def poll(self):
        if self.closed:
            return
        if self.guard and self.guard.requested():
            self.from_clipboard()
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind = event.get('kind')
            if kind in ('show', 'hotkey'):
                self.from_clipboard()
            elif kind == 'quit':
                self.quit()
                return
            elif kind == 'idle':
                self.status.set(f'模型已释放 · {self.shortcut} 随时唤起')
            else:
                self.handle_result(event)
        self._poll_job = self.root.after(75, self.poll)

    def copy_translation(self):
        if self.last_translation:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.last_translation)
            self.status.set('译文已复制')

    def selected_term(self):
        for widget in (self.source, self.output):
            try:
                selected = widget.get('sel.first', 'sel.last').strip()
                if selected and any(c.isascii() and c.isalpha() for c in selected):
                    return selected
            except tk.TclError:
                pass
        text = self.get_source().strip()
        return text if len(text) <= 120 and '\n' not in text else ''

    def lookup(self):
        term = self.selected_term()
        if not term:
            term = simpledialog.askstring('联网查词', '输入要查询的英文术语：', parent=self.root)
        if term and term.strip():
            url = 'https://www.bing.com/search?' + urlencode({'q': term.strip() + ' STM32 中文 含义'})
            try:
                webbrowser.open(url)
            except Exception as exc:
                messagebox.showerror('无法打开浏览器', str(exc), parent=self.root)

    def term_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title('保存术语')
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.configure(background='#f6f8fb')
        frame = ttk.Frame(dialog, padding=15)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='英文术语').pack(anchor='w')
        term = ttk.Entry(frame, width=38, font=('Consolas', 10))
        term.pack(fill='x', pady=(5, 10))
        candidate = self.selected_term()
        term.insert(0, candidate)
        ttk.Label(frame, text='确认后的中文释义').pack(anchor='w')
        meaning = tk.Text(frame, width=35, height=4, wrap='word', font=('Microsoft YaHei UI', 10))
        meaning.pack(fill='x', pady=(5, 10))
        existing = self.store.exact_term(candidate) if candidate else None
        if existing:
            meaning.insert('1.0', existing['meaning'])
        elif candidate and len(self.last_translation) < 200:
            meaning.insert('1.0', self.last_translation)
        def save():
            try:
                self.store.save_term(term.get(), meaning.get('1.0', 'end-1c'))
            except Exception as exc:
                messagebox.showerror('保存未完成', str(exc), parent=dialog)
                return
            self.status.set('术语已保存，下次离线优先使用')
            dialog.destroy()
        def delete():
            if self.store.exact_term(term.get()):
                self.store.delete_term(term.get())
                self.status.set('已删除该术语')
                dialog.destroy()
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x')
        ttk.Button(buttons, text='删除该术语', command=delete).pack(side='left')
        ttk.Button(buttons, text='保存', command=save, style='Accent.TButton').pack(side='right')
        dialog.bind('<Escape>', lambda _: dialog.destroy())
        dialog.grab_set()
        term.focus_set()

    def hotkey_dialog(self):
        value = simpledialog.askstring('修改快捷键', '例如 Ctrl+Alt+T 或 Ctrl+Shift+F9：', initialvalue=self.shortcut, parent=self.root)
        if not value:
            return
        service = None
        try:
            _, _, normalized = native.parse_hotkey(value)
            if self.hotkey and not self.hotkey.error and normalized == self.shortcut:
                return
            service = native.Hotkey(value, self.events)
            if not service.start():
                raise ValueError(service.error)
            self.store.set_setting('hotkey', service.shortcut)
        except Exception as exc:
            if service:
                service.close()
            messagebox.showerror('快捷键未修改', str(exc), parent=self.root)
            return
        if self.hotkey:
            self.hotkey.close()
        self.hotkey = service
        self.shortcut = service.shortcut
        self.status.set(f'快捷键已改为 {self.shortcut}')

    def open_data_directory(self):
        import os
        os.startfile(str(self.data_dir))

    def start_services(self):
        try:
            self.hotkey = native.Hotkey(self.shortcut, self.events)
            if not self.hotkey.start():
                self.status.set(self.hotkey.error)
                messagebox.showwarning('快捷键冲突', self.hotkey.error, parent=self.root)
        except ValueError as exc:
            self.status.set(str(exc))
        try:
            import pystray
            self.tray = pystray.Icon('STM32Translate', make_icon(), 'STM32 译窗 · ' + self.shortcut,
                menu=pystray.Menu(
                    pystray.MenuItem('打开 / 翻译剪贴板', lambda *args: self.events.put({'kind': 'show'}), default=True),
                    pystray.MenuItem('退出', lambda *args: self.events.put({'kind': 'quit'})),
                ))
            self.tray.run_detached()
        except Exception as exc:
            self.tray = None
            messagebox.showwarning('托盘不可用', '可继续使用快捷键唤起；通过设置菜单退出。\n' + str(exc), parent=self.root)

    def quit(self):
        if self.closed:
            return
        self._save_geometry()
        self.closed = True
        for job in (self._poll_job, self._save_job):
            if job:
                self.root.after_cancel(job)
        if self.hotkey:
            self.hotkey.close()
        if self.tray:
            self.tray.stop()
        self.client.close()
        self.store.close()
        if self.guard:
            self.guard.close()
        self.root.destroy()


def main():
    native.enable_dpi_awareness()
    guard = native.InstanceGuard()
    if guard.already_running:
        guard.notify()
        guard.close()
        return
    root = tk.Tk()
    app = App(root, data_directory())
    app.guard = guard
    app.show()
    app.start_services()
    root.mainloop()
