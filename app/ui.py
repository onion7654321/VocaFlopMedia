"""Flet 1.x desktop interface: video cards, inline formats and quality, bottom status."""
from __future__ import annotations
import asyncio
import os
import json
import subprocess
from pathlib import Path
from uuid import uuid4
from typing import Any

import flet as ft
import flet_video as ftv

from . import __version__
from .branding import LOGO
from .filenames import safe_name, rename_file, download_folder, existing_download
from .formats import AUDIO_FORMATS, VIDEO_FORMATS, available_formats, quality_choices, quality_label, output_extension
from .models import MediaItem, DownloadJob
from .queue_state import queue_action, ready_to_shutdown
from .helpers import (extract_urls, clean_pasted_text, fmt_time, to_seconds, is_playlist,
                      source_name, parse_source_summary, can_download)
from .storage import load_settings, save_settings, History
from .toolchain import resolve_tool
from .tool_updates import check_deno, check_ffmpeg, install_tool
from .platforms import open_directory, shutdown_command, package_manager_hint, system
from .core import (check_ytdlp_update, install_ytdlp, check_app_update, stage_app_update,
                   probe, download, ffmpeg_dir, cli_exe, discard_partial)

BLUE = "#079355"
RED = "#FA646F"
GREEN = "#24B58D"
DARK = "#171717"
CARD_DARK = "#222222"
CARD_LIGHT = "#FFFFFF"
MUTED_DARK = "#B9B9B9"
MUTED_LIGHT = "#68768D"


class VocaflopUI:
    def __init__(self, page: ft.Page):
        self.page = page
        self.settings = load_settings()
        self.history = History()
        self.items: dict[str, MediaItem] = {}
        self.cancel_flags: dict[str, asyncio.Event] = {}
        self.stop_flags: dict[str, asyncio.Event] = {}
        self.jobs: dict[str, DownloadJob] = {}
        self.stop_button = None
        self.cancel_button = None
        self.shutdown_enabled = False
        self.shutdown_task = None
        self.pending_downloads = 0
        self.batch_dispatches = 0
        self.cycle_results: dict[str, str] = {}
        self.rename_drafts: dict[str, str] = {}
        self.clipboard = ft.Clipboard()
        self.last_clipboard_links = None
        self.removing_items: set[str] = set()
        self.preview_tasks: dict[str, asyncio.Task] = {}
        self.current_tab = "Downloads"
        self.mode = "video"
        self.batch_mode = "individual"   # Individual cards vs one shared format/quality
        self.shared_kind = "mp3"
        self.shared_quality = 320
        self.show_shared_qualities = False
        self.pending_ytdlp = False
        self.pending_tools: dict[str, dict] = {}
        self._tools_check_errors: dict[str, str] = {}
        self.pending_app_update: dict | None = None
        self.update_busy = False
        self.checking_updates = False
        self._input_revision = 0
        self._preview_limit = asyncio.Semaphore(3)
        self._replace_dialog_lock = asyncio.Lock()
        self._download_limit = asyncio.Semaphore(max(1, min(5, int(self.settings["parallel_jobs"]))))
        self._stream_limit = asyncio.Semaphore(1)
        self._last_log = ""
        self._notice_scope = None
        self._progress_last_update = 0.0
        self.player_dialog = None
        self.links_collapsed = False
        self.videos_compact = False
        self.expanded_history: set[str] = set()
        self.video_list = None
        self.link_summary = None
        self.batch_area = None
        self._setting_path_fields = {}
        self._tool_status_list = None
        self._cookie_file_field = None
        self._theme_buttons = {}
        self._settings_cards = []
        self.video_count = None
        self.source_summary = None
        
        self.apply_theme()
        page.title = f"Vocaflop {__version__}"
        page.padding = 0
        page.spacing = 0
        page.window.width = 1220
        page.window.height = 850
        page.window.min_width = 800
        page.window.min_height = 550
        # Preserve input focus and undo history.
        self.url_input = ft.TextField(
            hint_text="Paste one per line, or separate with commas or spaces",
            multiline=True, shift_enter=False, fit_parent_size=True, height=175,
            border=ft.NoInputBorder(), filled=False,
            content_padding=14,
            on_change=self.on_urls_changed, on_click=self.paste_clipboard_links,
        )

        self.update_button = self.button(content="Update", icon=ft.Icons.SYSTEM_UPDATE_ALT,
                                      bgcolor=BLUE, color="#FFFFFF", visible=False,
                                      on_click=lambda e: page.run_task(self.apply_updates))
        self.error_icon = ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=GREEN, size=18)
        self.footer_text = ft.Text("Ready", size=12, expand=True, max_lines=1)
        self.shutdown_cancel = ft.TextButton(content="Cancel shutdown", visible=False, on_click=self.cancel_shutdown)
        self.footer_details = ft.TextButton(content="Details", visible=False, on_click=self.show_last_error)
        self.content = ft.Container(expand=True, padding=ft.Padding.symmetric(horizontal=28, vertical=18))
        self.header = ft.Container(padding=ft.Padding.symmetric(horizontal=28, vertical=17),
                                   content=ft.Row(spacing=12, controls=[
            ft.Image(src=LOGO, width=88, height=49, fit=ft.BoxFit.CONTAIN),
            ft.Text("Media Downloader", weight=ft.FontWeight.BOLD, size=20),
            ft.Container(expand=True),
            self.update_button,
        ]))
        self.navigation = ft.Row(spacing=8, controls=[])
        self.footer = ft.Container(padding=ft.Padding.symmetric(horizontal=25, vertical=9),
                                   content=ft.Row(spacing=8, controls=[self.error_icon, self.footer_text, self.shutdown_cancel, self.footer_details]))
        page.add(ft.Column(expand=True, spacing=0, controls=[
            self.header,
            ft.Container(padding=ft.Padding.symmetric(horizontal=28), content=self.navigation),
            ft.Divider(height=18, thickness=1, color="#9C9C9C"),
            self.content,
            self.footer,
        ]))
        self.select_tab("Downloads")
        if self.settings.get("check_updates", True):
            page.run_task(self.auto_check_updates)


    def toggle_link_area(self, e=None):
        self.links_collapsed = not self.links_collapsed
        self.render_downloads()
        self.page.update()

    def toggle_video_compact(self, e=None):
        self.videos_compact = not self.videos_compact
        for item in self.items.values():
            item.collapsed = self.videos_compact
        self.refresh_video_list()

    def toggle_video_card(self, item: MediaItem):
        item.collapsed = not item.collapsed
        self.refresh_video_list()

    def refresh_video_list(self):
        """Update only video list; do NOT remount the URL input during editing."""
        if self.current_tab != 'Downloads':
            return
        if self.video_list is not None:
            self.video_list.controls = ([self.build_card(i) for i in self.items.values()] or
                [self.box(ft.Container(height=100, alignment=ft.Alignment.CENTER,
                     content=self.secondary('Paste a link to get started.')))])
        urls = [u for u in extract_urls(self.url_input.value or '', self.mode) if can_download(u)]
        if self.link_summary is not None:
            self.link_summary.value = parse_source_summary(urls)
        if self.source_summary is not None:
            self.source_summary.value = parse_source_summary(urls)
        if self.video_count is not None:
            self.video_count.value = f'{len(self.items)} items'
        self.refresh_queue_actions()
        self.page.update()

    def refresh_queue_actions(self):
        action, enabled = queue_action(self.items.values())
        if self.stop_button is not None:
            self.stop_button.visible = action is not None
            self.stop_button.content = action or "Stop all"
            self.stop_button.icon = ft.Icons.PLAY_ARROW if action == "Resume all" else ft.Icons.STOP
            self.stop_button.disabled = not enabled
        if self.cancel_button is not None:
            self.cancel_button.visible = action is not None

    def palette(self):
        if self.settings.get("theme") == "light":
            return ("#F4F6FB", CARD_LIGHT, MUTED_LIGHT, "#DBE2EF")
        return (DARK, CARD_DARK, MUTED_DARK, "#3D3D3D")

    def apply_theme(self):
        dark = self.settings.get("theme") != "light"
        self.page.theme_mode = ft.ThemeMode.DARK if dark else ft.ThemeMode.LIGHT
        self.page.theme = ft.Theme(color_scheme_seed="#737373", color_scheme=ft.ColorScheme(primary=BLUE, on_primary="#FFFFFF"))
        self.page.dark_theme = ft.Theme(color_scheme_seed="#737373", color_scheme=ft.ColorScheme(primary="#E9E9E9", on_primary="#202020"))
        self.page.bgcolor = DARK if dark else "#F4F6FB"
    def neutral_button_bg(self):
        return "#FFFFFF" if self.settings.get("theme") == "light" else "#343434"

    def neutral_button_fg(self):
        return "#242424" if self.settings.get("theme") == "light" else "#FFFFFF"

    def button(self, *args, **kwargs):
        bg = kwargs.get("bgcolor")
        if bg not in (BLUE, RED):
            kwargs["bgcolor"] = self.neutral_button_bg()
            kwargs["color"] = self.neutral_button_fg()
        else:
            kwargs["color"] = "#FFFFFF"
        return ft.Button(*args, **kwargs)

    def link_editor_bg(self):
        return "#F3F3F3" if self.settings.get("theme") == "light" else "#242424"


    def box(self, control, *, padding=18, expand=False):
        _, card_color, _, border_color = self.palette()
        return ft.Container(content=control, padding=padding, expand=expand,
                            bgcolor=card_color, border_radius=15,
                            border=ft.Border.all(1, border_color))

    def secondary(self, message, size=12, **kwargs):
        return ft.Text(message, color=self.palette()[2], size=size, **kwargs)

    def notice(self, message: str, *, error=False, log="", scope=None):
        self._notice_scope = scope
        self.error_icon.name = ft.Icons.ERROR_OUTLINE if error else ft.Icons.CHECK_CIRCLE_OUTLINE
        self.error_icon.color = RED if error else GREEN
        self.footer_text.value = str(message)[:450]
        self._last_log = log or str(message)
        self.footer_details.visible = bool(error)
        self.page.update()

    def clear_notice(self, scope):
        if scope is not None and self._notice_scope == scope:
            self.notice("Ready")

    def show_last_error(self, e=None):
        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("Error details"),
            content=ft.Container(width=650, height=350, content=ft.Column(
                scroll=ft.ScrollMode.AUTO,
                controls=[ft.Text(self._last_log or "No error details.", selectable=True, size=12)])),
            actions=[ft.TextButton(content="Close", on_click=lambda _: self.page.pop_dialog())]))

    def render_navigation(self):
        tab = self.current_tab
        self.navigation.controls = [
            self.button(content=label, icon={"Downloads": ft.Icons.DOWNLOAD_ROUNDED,
                "History": ft.Icons.HISTORY_ROUNDED, "Settings": ft.Icons.TUNE_ROUNDED}[label],
                bgcolor=BLUE if tab == label else "#FFFFFF" if self.settings.get("theme") == "light" else "#1A2235",
                color="#FFFFFF" if tab == label else BLUE,
                on_click=lambda e, t=label: self.select_tab(t))
            for label in ("Downloads", "History", "Settings")]

    def select_tab(self, tab: str):
        self.current_tab = tab
        self.render_navigation()
        if tab == "Downloads":
            self.render_downloads()
        elif tab == "History":
            self.render_history()
        else:
            self.render_settings()
        self.page.update()

    # Downloads
    def set_mode(self, new_mode: str):
        if any(i.busy or i.status == "Stopped" for i in self.items.values()):
            self.notice("Finish or cancel downloads before changing mode.", error=True)
            return
        self.mode = new_mode
        # One mode at a time. Rebuild preview cards if mode changes.
        self.items.clear()
        self.rename_drafts.clear()
        self.on_urls_changed()
        self.render_downloads()
        self.page.update()

    async def paste_clipboard_links(self, e):
        field = e.control
        try:
            text = await self.clipboard.get()
        except Exception:
            return
        if not isinstance(text, str):
            return
        links = tuple(u for u in extract_urls(text, self.mode) if can_download(u))
        if links == self.last_clipboard_links:
            return
        self.last_clipboard_links = links
        if not links:
            return
        existing = set(extract_urls(field.value or "", self.mode))
        additions = [u for u in links if u not in existing]
        if not additions:
            return
        field.value = "\n".join(filter(None, [(field.value or "").strip(), *additions]))
        field.update()
        if field is self.url_input:
            self.on_urls_changed()

    def on_urls_changed(self, e=None):
        self._input_revision += 1
        n = self._input_revision
        self.page.run_task(self._parse_input_after_delay, n)

    async def _parse_input_after_delay(self, revision: int, delay: float = .4):
        if delay:
            await asyncio.sleep(delay)
        if revision != self._input_revision:
            return
        discovered = extract_urls(self.url_input.value or "", self.mode)
        disabled = sorted({source_name(u) for u in discovered if not can_download(u)})
        urls = [u for u in discovered if can_download(u)]
        if disabled and revision == self._input_revision:
            reason = (" Spotify full-track downloads are unavailable; use its official offline mode."
                      if 'Spotify' in disabled else '')
            self.notice(f"Unavailable: {', '.join(disabled)}.{reason}", error=True, scope="links")
        if self.mode == "playlist":
            urls = [url for url in urls if is_playlist(url)]
        if (self.url_input.value or "").strip() and not urls and revision == self._input_revision:
            if not disabled:
                self.notice("No downloadable links. Supported: YouTube, Niconico, Facebook, X, SoundCloud.", error=True, scope="links")
        elif not disabled:
            self.clear_notice("links")
        # Preserve cards and selections between edits; don't remove running jobs.
        old = {(x.url, x.mode): x for x in self.items.values()}
        updated: dict[str, MediaItem] = {}
        for url in urls[:80]:
            key = (url, self.mode)
            item = old.get(key)
            if item is None:
                item = MediaItem(url=url, mode=self.mode)
                if source_name(url) == 'SoundCloud':
                    item.kind = 'mp3'
                if self.mode == "stream":
                    item.status = "Checking live stream..."
            updated[item.id] = item
        for item in self.items.values():
            if (item.busy or item.status == "Stopped") and item.id not in updated:
                updated[item.id] = item
        self.items = updated
        self.rename_drafts = {k: v for k, v in self.rename_drafts.items() if k in updated}
        if self.current_tab == "Downloads":
            self.refresh_batch_controls()
            self.refresh_video_list()
        for item in updated.values():
            if not can_download(item.url):
                item.status = 'Unsupported source'
                item.title = f'{source_name(item.url)} · extractor unavailable'
                item.error = 'This source cannot be downloaded.'
                item.preview_ready = True
                continue
            if not item.preview_ready and item.id not in self.preview_tasks:
                task = asyncio.create_task(self.fetch_preview(item))
                self.preview_tasks[item.id] = task
                task.add_done_callback(lambda t, key=item.id: self.preview_tasks.pop(key, None))
        if len(urls) > 80:
            self.notice("Showing the first 80 links; use a smaller batch.", error=True)

    async def import_txt(self, e):
        files = await ft.FilePicker().pick_files(
            allow_multiple=False, file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["txt"], dialog_title="Import links from TXT")
        if not files:
            return
        path = files[0].path
        if not path:
            self.notice("A local TXT file is required.", error=True)
            return
        try:
            if Path(path).stat().st_size > 2_000_000:
                raise ValueError("TXT file is larger than 2 MB.")
            data = await asyncio.to_thread(Path(path).read_text, encoding="utf-8-sig")
        except Exception as ex:
            self.notice(str(ex), error=True)
            return
        self.url_input.value = ((self.url_input.value or "") + "\n" + data).strip()
        self.url_input.update()
        self.on_urls_changed()

    def set_batch_mode(self, mode: str):
        if mode not in ('individual', 'shared'):
            return
        self.batch_mode = mode
        self.refresh_batch_controls()

    def refresh_batch_controls(self):
        # Update batch controls without remounting the input.
        if self.current_tab == 'Downloads' and self.batch_area is not None:
            self.batch_area.controls = self.batch_controls()
            self.batch_area.update()

    def set_shared_kind(self, kind: str):
        self.shared_kind = kind
        self.shared_quality = self.shared_qualities()[0]
        self.show_shared_qualities = True
        self.refresh_batch_controls()

    def shared_qualities(self) -> list[int]:
        all_res = sorted({r for it in self.items.values() for r in it.resolutions}, reverse=True)
        return quality_choices(self.shared_kind, all_res)

    def choose_shared_quality(self, quality: int):
        self.shared_quality = quality
        self.show_shared_qualities = True
        self.refresh_batch_controls()

    def batch_controls(self):
        active = lambda which: BLUE if self.batch_mode == which else None
        color = lambda which: '#FFFFFF' if self.batch_mode == which else None
        controls = [
            ft.Row(spacing=13, wrap=True, controls=[
                ft.Text('BATCH OPTIONS', size=12, weight=ft.FontWeight.BOLD, color=self.palette()[2]),
                self.button(content='Individual settings', bgcolor=active('individual') or ('#FFFFFF' if self.settings.get('theme') == 'light' else '#1A2235'),
                          color=color('individual'), on_click=lambda e: self.set_batch_mode('individual')),
                self.button(content='Same settings for all', bgcolor=active('shared') or ('#FFFFFF' if self.settings.get('theme') == 'light' else '#1A2235'),
                          color=color('shared'), on_click=lambda e: self.set_batch_mode('shared')),
            ]),
        ]
        if self.batch_mode == 'shared':
            if self.items and all(source_name(i.url) == 'SoundCloud' for i in self.items.values()) and self.shared_kind not in AUDIO_FORMATS:
                self.shared_kind = 'mp3'
            choices = self.shared_qualities()
            if self.shared_quality not in choices:
                self.shared_quality = choices[0]
            controls.append(ft.Row(wrap=True, spacing=14, run_spacing=10, controls=[
                ft.Dropdown(label='Format', width=150, value=self.shared_kind,
                    options=[ft.DropdownOption(key=k, text=k.upper()) for k in available_formats(bool(self.items) and all(source_name(i.url) == 'SoundCloud' for i in self.items.values()))],
                    on_select=lambda e: self.set_shared_kind(e.control.value)),
                self.secondary('Quality', size=12),
                *[self.button(content=quality_label(self.shared_kind, q),
                            bgcolor=BLUE if q == self.shared_quality else None,
                            color='#FFFFFF' if q == self.shared_quality else None,
                            on_click=lambda e, value=q: self.choose_shared_quality(value))
                  for q in choices],
            ]))
        return controls

    def clean_links(self, e=None):
        """Rewrite pasted text into one safe, canonical supported URL per line."""
        raw = self.url_input.value or ''
        urls = extract_urls(raw, self.mode)
        if not urls:
            self.notice('No recognized media links to clean.', error=True)
            return
        self.url_input.value = '\n'.join(urls)
        self.url_input.update()
        self.on_urls_changed()
        self.notice(f'Cleaned {len(urls)} links · tracking parameters and extra text removed.')

    def expand_urls(self, e=None):
        editor = ft.TextField(value=self.url_input.value or '', multiline=True,
                              fit_parent_size=True, height=495, border=ft.NoInputBorder(), filled=False,
                              content_padding=14, hint_text='Paste links, one per line', on_click=self.paste_clipboard_links)
        def save(_):
            self.url_input.value = editor.value or ''
            self.page.pop_dialog()
            self.url_input.update()
            self.on_urls_changed()
        self.page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text('Edit all links'),
            bgcolor=self.palette()[1],
            content=ft.Container(width=780, height=495, bgcolor=self.link_editor_bg(),
                                 border_radius=10, content=ft.Column(expand=True, spacing=0,
                                     horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                                     controls=[editor])),
            actions=[ft.TextButton(content='Cancel', on_click=lambda _: self.page.pop_dialog()),
                     self.button(content='Apply', bgcolor=BLUE, color='#FFFFFF', on_click=save)]))

    def render_downloads(self):
        light_theme = self.settings.get("theme") == "light"
        neutral_button = "#FFFFFF" if light_theme else "#1A2235"
        mode_controls = []
        for value, label, icon in [
            ('video', 'Videos', ft.Icons.MOVIE_OUTLINED),
            ('playlist', 'Playlist', ft.Icons.PLAYLIST_PLAY_ROUNDED),
            ('stream', 'Long stream', ft.Icons.SENSORS_ROUNDED),
        ]:
            mode_controls.append(self.button(
                content=label, icon=icon,
                bgcolor=BLUE if self.mode == value else neutral_button,
                color='#FFFFFF' if self.mode == value else BLUE,
                on_click=lambda e, v=value: self.set_mode(v)))
        urls = extract_urls(self.url_input.value or '', self.mode)
        self.link_summary = ft.Text(parse_source_summary(urls), size=12, color=self.palette()[2], max_lines=1, expand=True)
        self.source_summary = ft.Text(parse_source_summary(urls), size=11, color=self.palette()[2], max_lines=1, width=280)
        self.video_count = ft.Text(f'{len(self.items)} items', size=12, color=self.palette()[2])

        links_header = ft.Row(spacing=8, controls=[
            ft.Icon(ft.Icons.LINK, size=17, color=BLUE),
            ft.Text('LINKS', size=12, weight=ft.FontWeight.BOLD),
            self.link_summary, self.video_count,
            ft.IconButton(icon=ft.Icons.UPLOAD_FILE_OUTLINED, tooltip="Import TXT",
                          icon_color=self.neutral_button_fg(), on_click=lambda e: self.page.run_task(self.import_txt, e)),
            ft.IconButton(icon=ft.Icons.OPEN_IN_FULL, tooltip="Full editor",
                          icon_color=self.neutral_button_fg(), on_click=self.expand_urls),
            ft.IconButton(icon=ft.Icons.EXPAND_MORE if self.links_collapsed else ft.Icons.EXPAND_LESS,
                          tooltip='Expand' if self.links_collapsed else 'Collapse',
                          icon_color=self.neutral_button_fg(), on_click=self.toggle_link_area),
        ])
        input_controls = [ft.Container(
            visible=not self.links_collapsed, height=175, border_radius=10,
            bgcolor=self.link_editor_bg(), content=self.url_input,
        )]
        self.stop_button = ft.TextButton(content="Stop all", icon=ft.Icons.STOP, on_click=self.stop_all)
        self.cancel_button = ft.TextButton(content="Cancel all", icon=ft.Icons.CANCEL_OUTLINED, on_click=self.cancel_all)
        self.refresh_queue_actions()
        self.batch_area = ft.Column(spacing=8, controls=self.batch_controls())
        entry = self.box(ft.Column(spacing=10,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                links_header,
                *input_controls,
                ft.Divider(height=5, color=self.palette()[3]),
                self.batch_area,
                ft.Row(controls=[self.source_summary, ft.Container(expand=True),
                    self.button(content='Download', icon=ft.Icons.DOWNLOAD_ROUNDED,
                              bgcolor=BLUE, color='#FFFFFF',
                              on_click=lambda e: self.page.run_task(self.download_all))]),
            ]), padding=16)
        # Use a single scrolling area.
        self.video_list = ft.Column(spacing=10,
            controls=([self.build_card(i) for i in self.items.values()] or
                      [self.box(ft.Container(height=90, alignment=ft.Alignment.CENTER,
                                content=self.secondary('Paste a link to get started.')))]))
        self.content.content = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO,
                                       horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                                       spacing=13, controls=[
            ft.Row(spacing=12, controls=[
                ft.Column(spacing=3, controls=[ft.Text('Downloads', size=23, weight=ft.FontWeight.BOLD),
                    self.secondary('YouTube · SoundCloud · Niconico · X · Facebook')]),
                ft.Container(expand=True),
                ft.Row(wrap=True, spacing=6, controls=mode_controls),
            ]),
            entry,
            ft.Row(controls=[ft.Text('VIDEOS' if self.mode == 'video' else self.mode.upper(),
                                     size=12, weight=ft.FontWeight.BOLD, color=self.palette()[2]),
                             ft.Container(expand=True),
                             ft.TextButton(content='Detailed' if self.videos_compact else 'Compact',
                                           icon=ft.Icons.UNFOLD_MORE if self.videos_compact else ft.Icons.UNFOLD_LESS,
                                           on_click=self.toggle_video_compact),
                             self.stop_button, self.cancel_button,
                             ft.TextButton(content='Clear', on_click=self.clear_items)]),
            self.video_list,
        ])

    def confirm(self, title, message, action, callback):
        def accept(e):
            self.page.pop_dialog()
            callback()
        self.page.show_dialog(ft.AlertDialog(modal=True, bgcolor=self.neutral_button_bg(), title=ft.Text(title),
            content=ft.Text(message), actions=[
                ft.TextButton(content="No", on_click=lambda e: self.page.pop_dialog()),
                self.button(content=action, bgcolor=RED, color="#FFFFFF", on_click=accept)]))

    async def confirm_replace(self, name):
        loop = asyncio.get_running_loop()
        answer = loop.create_future()
        def choose(value):
            def resolve():
                if not answer.done():
                    answer.set_result(value)
            loop.call_soon_threadsafe(resolve)
        def respond(value):
            choose(value)
            self.page.pop_dialog()
        self.page.show_dialog(ft.AlertDialog(modal=True, bgcolor=self.neutral_button_bg(),
            title=ft.Text("Replace file?"), content=ft.Text(name),
            on_dismiss=lambda e: choose(False), actions=[
                ft.TextButton(content="Cancel", on_click=lambda e: respond(False)),
                self.button(content="Replace", bgcolor=BLUE, color="#FFFFFF", on_click=lambda e: respond(True))]))
        return await answer

    def clear_items(self, e):
        def clear():
            self._input_revision += 1
            self.url_input.value = ""
            self.items = {k: v for k, v in self.items.items() if v.busy or v.status == "Stopped"}
            if isinstance(self._notice_scope, tuple) and self._notice_scope[0] in {"cut", "name", "preview"} and self._notice_scope[1] not in self.items:
                self.clear_notice(self._notice_scope)
            self.rename_drafts.clear()
            self.clear_notice("links")
            self.render_downloads()
            self.page.update()
        self.confirm("Clear?", "Remove items?", "Clear", clear)

    def stop_one(self, item):
        if item.busy and item.id in self.stop_flags and item.status not in {"Stopping...", "Cancelling..."}:
            self.stop_flags[item.id].set()
            item.status = "Stopping..."
            self.refresh_video_list()

    def resume_one(self, item):
        if item.status == "Stopped" and item.id in self.jobs:
            self.page.run_task(self.download_one, item, self.jobs[item.id].quality)

    def stop_all(self, e=None):
        if any(i.busy for i in self.items.values()):
            for item in self.items.values():
                if item.busy and item.id in self.stop_flags and item.status not in {"Stopping...", "Cancelling..."}:
                    self.stop_flags[item.id].set()
                    item.status = "Stopping..."
            self.refresh_video_list()
        else:
            self.page.run_task(self.resume_all)

    async def resume_all(self):
        targets = [i for i in self.items.values() if i.status == "Stopped" and i.id in self.jobs]
        self.batch_dispatches += 1
        try:
            await asyncio.gather(*(self.download_one(i, self.jobs[i.id].quality) for i in targets))
        finally:
            self.batch_dispatches -= 1
            self.maybe_shutdown()

    def cancel_all(self, e=None):
        self.confirm("Cancel all?", "Discard downloads?", "Cancel all", self._cancel_all)

    def _cancel_all(self):
        for item in list(self.items.values()):
            self._cancel_item(item)
        self.refresh_video_list()

    def _cancel_item(self, item):
        if item.busy or item.status == "Stopped":
            self.cycle_results[item.id] = "Cancelled"
            self.cancel_shutdown_countdown()
        flag = self.cancel_flags.get(item.id)
        if flag is not None:
            flag.set()
            item.status = "Cancelling..."
        elif item.status == "Stopped" and item.id in self.jobs:
            try:
                discard_partial(self.jobs[item.id])
                item.status = "Cancelled"
                item.progress = 0
                self.history.update(self.jobs[item.id].id, "Cancelled", self.jobs[item.id].completed_files)
                self.jobs.pop(item.id, None)
            except OSError as ex:
                self.notice(f"Cannot remove temporary files: {ex}", error=True)

    def save_item_name(self, item, value):
        name = safe_name(value or "")
        extension = "." + output_extension(item.kind)
        if name.lower().endswith(extension):
            name = safe_name(name[:-len(extension)])
        item.filename = name
        self.rename_drafts.pop(item.id, None)
        return name

    def commit_pending_name(self, item):
        if item.id in self.rename_drafts:
            self.save_item_name(item, self.rename_drafts[item.id])

    def title_control(self, item, size, lines):
        display_name = item.filename or (Path(item.downloaded_file).stem if item.downloaded_file else item.title)
        label = ft.Text(display_name, size=size, max_lines=lines, weight=ft.FontWeight.BOLD)
        if item.busy or item.mode == "playlist" or item.status == "Stopped":
            return label
        editing = item.id in self.rename_drafts
        field = ft.TextField(value=self.rename_drafts.get(item.id, display_name),
                             dense=True, expand=True, visible=editing,
                             text_size=size)

        def draft_changed(e):
            if field.visible and item.id in self.rename_drafts:
                self.rename_drafts[item.id] = e.control.value

        field.on_change = draft_changed

        async def begin(e):
            if field.visible or item.id not in self.items:
                return
            field.value = item.filename or (Path(item.downloaded_file).stem if item.downloaded_file else item.title)
            self.rename_drafts[item.id] = field.value
            trigger.visible = False
            field.visible = True
            row.update()
            await field.focus()

        def commit(e=None):
            if not field.visible or item.id not in self.rename_drafts or item.id not in self.items:
                return
            try:
                name = self.save_item_name(item, field.value)
                label.value = name
                if item.error in {"A file with that name already exists. Rename it before downloading.", "Another download is using that filename."}:
                    item.error = ""
                    item.status = "Ready"
                self.clear_notice(("name", item.id))
            except (ValueError, OSError) as ex:
                self.notice(str(ex), error=True, scope=("name", item.id))
                return
            field.visible = False
            trigger.visible = True
            row.update()

        trigger = ft.GestureDetector(content=label, mouse_cursor=ft.MouseCursor.TEXT,
                                     on_tap=begin, expand=True, visible=not editing)
        field.on_submit = commit
        field.on_blur = commit
        field.on_tap_outside = commit
        row = ft.Row(spacing=0, controls=[trigger, field])
        return row

    async def fetch_preview(self, item: MediaItem):
        async with self._preview_limit:
            try:
                data = await probe(item.url, playlist=(item.mode == "playlist"))
                # Dropped cards shouldn't be restored by late results.
                if item.id not in self.items:
                    return
                item.title = data["title"]
                item.channel = data["channel"]
                item.thumbnail = data["thumbnail"]
                item.duration = data["duration"]
                item.resolutions = data["resolutions"]
                item.is_live = data["is_live"]
                item.playback_url = data.get("playback_url", "")
                if not item.busy and item.status not in {"Completed", "Stopped", "Cancelled"}:
                    if item.status in {"Preview failed", "Preview unavailable"}:
                        item.error = ""
                        self.clear_notice(("preview", item.id))
                    item.status = "Ready"
                    if item.mode == "stream" and not item.is_live:
                        item.status = "Ready · Non-live video"
                item.preview_ready = True
            except Exception as ex:
                if item.id not in self.items:
                    return
                if not item.busy and item.status not in {"Completed", "Stopped", "Cancelled"}:
                    if item.playback_url or (item.downloaded_file and Path(item.downloaded_file).is_file()):
                        item.status = "Ready"
                        self.clear_notice(("preview", item.id))
                    else:
                        item.status = "Preview unavailable"
                    item.error = ""
                # Metadata failure doesn't prevent a download attempt.
                item.preview_ready = True
                item.log = getattr(ex, "diagnostic", str(ex))
            if self.current_tab == "Downloads":
                self.refresh_video_list()

    def set_kind(self, item: MediaItem, kind: str):
        if item.busy or item.status == "Stopped":
            return
        if kind not in available_formats(source_name(item.url) == 'SoundCloud'):
            self.notice('Choose a supported format.', error=True)
            return
        item.kind = kind
        item.show_qualities = False
        item.quality = None
        self.refresh_video_list()

    def select_quality(self, item, quality):
        if item.busy or item.status == "Stopped":
            return
        first_selection = item.quality is None
        item.quality = quality
        self.refresh_video_list()
        if first_selection:
            self.page.run_task(self.reveal_item_actions, item.id)

    async def reveal_item_actions(self, item_id):
        await asyncio.sleep(.05)
        if self.current_tab == "Downloads" and item_id in self.items:
            try:
                await self.content.content.scroll_to(delta=58, duration=180)
            except Exception:
                pass

    def toggle_quality(self, item: MediaItem):
        item.show_qualities = not item.show_qualities
        self.refresh_video_list()

    def remove_item(self, item: MediaItem):
        if item.id not in self.items or item.id in self.removing_items:
            return
        if item.busy or item.status == "Stopped":
            self._cancel_item(item)
            if item.status == "Stopped":
                return
        raw_urls = extract_urls(self.url_input.value or "", self.mode)
        self.url_input.value = "\n".join(url for url in raw_urls if url != item.url)
        self.rename_drafts.pop(item.id, None)
        self.clear_notice(("cut", item.id))
        self.clear_notice(("name", item.id))
        self.clear_notice(("preview", item.id))
        if item.busy:
            self.removing_items.add(item.id)
        else:
            self.items.pop(item.id, None)
        self.on_urls_changed()
        self.refresh_video_list()

    def item_actions(self, item: MediaItem):
        if item.busy or item.status == "Stopped":
            stopped = item.status == "Stopped"
            return [
                self.button(content="Resume" if stopped else "Stop", icon=ft.Icons.PLAY_ARROW if stopped else ft.Icons.STOP,
                          bgcolor=BLUE if stopped else ("#FFFFFF" if self.settings.get("theme") == "light" else "#1A2235"),
                          color="#FFFFFF" if stopped else self.neutral_button_fg(),
                          disabled=item.status in {"Stopping...", "Cancelling..."},
                          on_click=lambda e: self.resume_one(item) if stopped else self.stop_one(item)),
                ft.TextButton(content="Cancel", icon=ft.Icons.CANCEL_OUTLINED,
                              disabled=item.status == "Cancelling...", on_click=lambda e: self.cancel_one(item)),
            ]
        completed = ([self.button(content="Open folder", icon=ft.Icons.FOLDER_OPEN,
                        on_click=lambda e: self.open_downloaded_files(item.downloaded_files or [item.downloaded_file]))]
                     if item.download_folder or item.downloaded_file else [])
        if item.quality is None:
            return completed
        return completed + [self.button(content="Download", icon=ft.Icons.DOWNLOAD_ROUNDED, bgcolor=BLUE, color="#FFFFFF",
                          disabled=not can_download(item.url), on_click=lambda e: self.page.run_task(self.download_one, item, item.quality))]

    def open_downloaded_files(self, files):
        file = existing_download(files)
        if not file:
            self.notice("Downloaded file no longer exists.", error=True, scope="folder")
            return
        self.open_folder(file)

    def open_folder(self, file="", folder=""):
        try:
            target = download_folder(file, folder)
            open_directory(target)
        except (OSError, ValueError) as ex:
            self.notice(str(ex), error=True, scope="folder")
        else:
            self.clear_notice("folder")

    def quality_buttons(self, item):
        if not item.preview_ready and item.kind in VIDEO_FORMATS:
            return [self.secondary("Loading qualities...")]
        return [self.button(content=quality_label(item.kind, q),
                    bgcolor=BLUE if q == item.quality else None,
                    on_click=lambda e, n=q: self.select_quality(item, n))
                for q in quality_choices(item.kind, item.resolutions, item.audio_rates)]

    def build_card(self, item: MediaItem):
        _, _, muted, _ = self.palette()
        tag = ("PLAYLIST" if item.mode == "playlist" else
               "STREAM" if item.mode == "stream" else source_name(item.url).upper())
        if item.collapsed:
            return self.box(ft.Row(spacing=12, controls=[
                ft.Container(bgcolor='#293C6D', border_radius=7, padding=7,
                             content=ft.Text(tag, size=10, color='#D8E4FF')),
                ft.Column(expand=True, spacing=2, controls=[
                    self.title_control(item, 13, 1),
                    self.secondary(f"{item.status}  ·  {str(item.kind).upper()}  ·  {int(item.progress * 100)}%", 11)]),
                *self.item_actions(item),
                ft.IconButton(icon=ft.Icons.EXPAND_MORE, tooltip='Expand video',
                              on_click=lambda e, i=item: self.toggle_video_card(i)),
                ft.IconButton(icon=ft.Icons.CLOSE, tooltip='Remove link',
                              on_click=lambda e, i=item: self.remove_item(i)),
            ]), padding=10)
        kind = ft.Dropdown(width=115, height=49, value=item.kind, disabled=item.busy or item.status == "Stopped", options=[
            ft.DropdownOption(key=k, text=k.upper()) for k in available_formats(source_name(item.url) == 'SoundCloud')],
            on_select=lambda e, m=item: self.set_kind(m, e.control.value))
        durations = f" · {fmt_time(item.duration)}" if item.duration is not None else ""
        tag = ("PLAYLIST" if item.mode == "playlist" else "STREAM" if item.mode == "stream" else source_name(item.url).upper())
        image = (ft.Image(src=item.thumbnail, width=170, height=96, fit=ft.BoxFit.COVER,
                          border_radius=ft.BorderRadius.all(9)) if item.thumbnail
                 else ft.Container(width=170, height=96, border_radius=9, bgcolor="#24314C",
                                   content=ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE, color="#8CA9FF", size=41),
                                   alignment=ft.Alignment.CENTER))
        if self.settings.get('video_preview') and item.mode == 'video' and (item.playback_url or item.downloaded_file):
            image = ft.Stack(width=170, height=96, controls=[image,
                ft.Container(width=170, height=96, alignment=ft.Alignment.CENTER,
                    content=ft.IconButton(icon=ft.Icons.PLAY_CIRCLE_FILLED, icon_size=44,
                        icon_color="#FFFFFF", bgcolor="#88000000", tooltip="Play preview",
                        on_click=lambda e, i=item: self.show_video_player(i)))])
        top = ft.Row(spacing=15, vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[image, ft.Column(expand=True, spacing=8, controls=[
                self.title_control(item, 16, 2),
                ft.Text(f"{item.channel}{durations}", color=muted, size=12, max_lines=1),
                ft.Row(spacing=8, controls=[
                    ft.Container(padding=ft.Padding.symmetric(horizontal=7, vertical=3),
                                 border_radius=6, bgcolor="#293C6D",
                                 content=ft.Text(tag, size=10, color="#D8E4FF")),
                    ft.Text(item.status, color=RED if item.error else muted, size=11, max_lines=1),
                ])
            ])])
        clip_fields = []
        cut_warning = ft.Row(visible=bool(item.cut_error), spacing=8, controls=[
            ft.Icon(ft.Icons.INFO_OUTLINE, color=RED, size=15),
            ft.Text(item.cut_error, size=11, color=RED, expand=True),
        ])
        if item.mode == "video":
            clip_fields = [self.secondary("CUT", size=11),
                ft.TextField(hint_text="Start · 00:00:00", value=item.start, width=165, height=45,
                             disabled=item.busy or item.status == "Stopped",
                             on_change=lambda e, i=item: self.edit_cut(i, "start", e.control.value, cut_warning)),
                self.secondary("to", size=11),
                ft.TextField(hint_text="End · Full", value=item.end, width=165, height=45,
                             disabled=item.busy or item.status == "Stopped",
                             on_change=lambda e, i=item: self.edit_cut(i, "end", e.control.value, cut_warning)),
                self.secondary("Blank = full video", size=11)]
        else:
            clip_fields = [self.secondary("Whole playlist" if item.mode == "playlist" else
                f"Live capture · max {self.settings['stream_limit_minutes']} min", size=11)]
        controls = [
            ft.Row(controls=[ft.Text(tag, size=10, color=muted), ft.Container(expand=True),
                 ft.IconButton(icon=ft.Icons.EXPAND_LESS, tooltip='Collapse video',
                     on_click=lambda e, i=item: self.toggle_video_card(i))]),
            top,
            ft.Row(spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                   wrap=True, controls=clip_fields),
            cut_warning,
            ft.Row(spacing=10, vertical_alignment=ft.CrossAxisAlignment.END, controls=[
                ft.Row(expand=True, wrap=True, spacing=8, run_spacing=8, controls=[
                    kind,
                    *([] if item.busy or item.status == "Stopped" else self.quality_buttons(item)),
                    *self.item_actions(item),
                    *([self.secondary(f"{int(item.progress * 100)}%")] if item.busy else []),
                ]),
                ft.IconButton(icon=ft.Icons.CLOSE, tooltip='Remove link', icon_color=RED,
                              on_click=lambda e, i=item: self.remove_item(i))]),
        ]
        action_row = controls.pop()
        if self.settings.get('video_preview') and item.preview_ready and item.mode == 'video' and not (item.playback_url or item.downloaded_file):
            controls.append(self.secondary('Direct preview unavailable. Download the media to play locally.', 11))
        if item.busy or item.progress > 0:
            controls.append(ft.ProgressBar(value=item.progress if item.progress > 0 else None,
                                           height=5, color=GREEN if item.status == "Completed" else BLUE))
        if item.error and not item.busy:
            controls.append(ft.Row(controls=[ft.Icon(ft.Icons.INFO_OUTLINE, color=RED, size=15),
                                              ft.Text(item.error[:130], size=11, color=RED)]))
        controls.append(action_row)
        return self.box(ft.Column(spacing=12, controls=controls), padding=15)

    def open_compact_for_download(self, item: MediaItem):
        item.collapsed = False
        item.show_qualities = item.status != "Stopped"
        self.refresh_video_list()

    def show_video_player(self, item: MediaItem):
        if not self.settings.get('video_preview'):
            return
        source = item.downloaded_file if item.downloaded_file and Path(item.downloaded_file).is_file() else item.playback_url
        if not source:
            self.notice('Preview not available. Download MP4 to play locally.', error=True)
            return
        # Native media_kit/Flet video player, not WebView (no Windows support).
        player = ftv.Video(playlist=[ftv.VideoMedia(source)], autoplay=False,
                           expand=True, fit=ft.BoxFit.CONTAIN,
                           on_error=lambda e: self.notice('Playback failed. This platform may block direct playback; downloaded MP4 can be played locally.', error=True))
        timestamp_status = ft.Text("", size=12, color=self.neutral_button_fg())

        async def copy_timestamp(e):
            try:
                position = await player.get_current_position()
                seconds = getattr(position, "in_seconds", None)
                if callable(seconds):
                    seconds = seconds()
                if seconds is None and hasattr(position, "total_seconds"):
                    seconds = position.total_seconds()
                stamp = fmt_time(max(0, int(seconds)))
                await self.clipboard.set(stamp)
                timestamp_status.value = f"Copied {stamp}"
                timestamp_status.update()
            except Exception:
                timestamp_status.value = "Timestamp unavailable"
                timestamp_status.update()

        def close_player(e=None):
            self.page.pop_dialog()
            self.player_dialog = None
        self.player_dialog = ft.AlertDialog(
            title=ft.Text(item.filename or item.title[:95]),
            bgcolor=self.palette()[1],
            content=ft.Container(width=850, height=480, bgcolor='#000000',
                                 content=player),
            actions=[timestamp_status, self.button(content='Copy timestamp', icon=ft.Icons.CONTENT_COPY, on_click=copy_timestamp),
                     self.button(content='Close', on_click=close_player)])
        self.page.show_dialog(self.player_dialog)

    def success_popup(self, message: str):
        # Separate transient confirmation and persistent bottom status.
        self.notice(message)
        self.page.show_dialog(ft.SnackBar(content=ft.Text(message, color="#FFFFFF"),
                                         bgcolor='#07513A', duration=5000,
                                         close_icon_color='#FFFFFF', show_close_icon=True))

    async def folder_for_batch(self) -> str | None:
        if not self.settings.get("ask_folder"):
            return self.settings["download_dir"]
        return await ft.FilePicker().get_directory_path(dialog_title="Select download folder")

    def edit_cut(self, item, field, value, warning):
        if item.busy or item.status == "Stopped":
            return
        setattr(item, field, value)
        if not item.cut_error:
            return
        self.check_cut(item, notify=False)
        warning.controls[1].value = item.cut_error
        warning.visible = bool(item.cut_error)
        warning.update()

    def check_cut(self, item, *, notify=True):
        scope = ("cut", item.id)
        try:
            result = self.validate_cut(item)
        except ValueError as ex:
            item.cut_error = str(ex)
            if notify or self._notice_scope == scope:
                self.notice(item.cut_error, error=True, scope=scope)
            return None
        item.cut_error = ""
        self.clear_notice(scope)
        return result

    def validate_cut(self, item: MediaItem) -> tuple[int | None, int | None]:
        if item.mode != "video" or not item.start.strip() and not item.end.strip():
            return None, None
        start = to_seconds(item.start) if item.start.strip() else 0
        end = to_seconds(item.end) if item.end.strip() else None
        if end is not None and end <= start:
            raise ValueError("End time must be after start time.")
        if item.duration and start >= item.duration:
            raise ValueError("Start time must be before the end of the video.")
        if item.duration and end is not None and end > item.duration:
            raise ValueError("End time exceeds video duration.")
        return start, end

    async def download_one(self, item: MediaItem, quality: int, folder: str | None = None,
                           kind_override: str | None = None):
        if item.busy:
            return
        self.cancel_shutdown_countdown()
        if self.pending_downloads == 0 and not self.batch_dispatches and not any(i.status == "Stopped" for i in self.items.values()):
            self.cycle_results.clear()
        self.pending_downloads += 1
        outcome = None
        try:
            outcome = await self._download_one(item, quality, folder, kind_override)
        finally:
            self.cycle_results[item.id] = outcome or "Not started"
            self.pending_downloads -= 1
            self.maybe_shutdown()

    async def _download_one(self, item: MediaItem, quality: int, folder: str | None = None,
                            kind_override: str | None = None):
        if item.busy or item.id not in self.items:
            return
        try:
            self.commit_pending_name(item)
            self.clear_notice(("name", item.id))
        except (ValueError, OSError) as ex:
            self.notice(str(ex), error=True, scope=("name", item.id))
            return
        if item.status == "Stopped" and item.id in self.jobs:
            item.busy = True
            item.status = "Queued"
            item.error = ""
            self.cancel_flags[item.id] = asyncio.Event()
            self.stop_flags[item.id] = asyncio.Event()
            self.refresh_video_list()
            await self._run_download(item, self.jobs[item.id])
            return item.status
        if (kind_override or item.kind) not in available_formats(source_name(item.url) == 'SoundCloud'):
            self.notice('Choose a supported output format.', error=True)
            return
        if not can_download(item.url):
            self.notice(f'{source_name(item.url)} is disabled. No download was started.', error=True)
            return
        cut = self.check_cut(item)
        if cut is None:
            self.refresh_video_list()
            return
        start, end = cut
        try:
            folder = folder or await self.folder_for_batch()
            if not folder or item.busy or item.id not in self.items:
                return
            replace_existing = False
            if item.filename and item.mode != "playlist":
                target = Path(folder) / (safe_name(item.filename) + "." + output_extension(kind_override or item.kind))
                reserved = {os.path.normcase(str((Path(j.folder) / (safe_name(j.filename) + "." + output_extension(j.kind))).resolve()))
                            for j in self.jobs.values() if j.filename and j.mode != "playlist"}
                if os.path.normcase(str(target.resolve())) in reserved:
                    raise FileExistsError("Another download is using that filename.")
                if target.exists():
                    async with self._replace_dialog_lock:
                        replace_existing = await self.confirm_replace(target.name)
                    if not replace_existing or item.busy or item.id not in self.items or target.name != safe_name(item.filename) + "." + output_extension(kind_override or item.kind):
                        return
                    if any(j.filename and j.mode != "playlist" and
                           os.path.normcase(str((Path(j.folder) / (safe_name(j.filename) + "." + output_extension(j.kind))).resolve())) == os.path.normcase(str(target.resolve())) for j in self.jobs.values()):
                        raise FileExistsError("Another download is using that filename.")
            item.kind = kind_override or item.kind
            item.quality = quality
            item.show_qualities = False
            item.busy = True
            item.progress = 0
            item.error = ""
            self.clear_notice(("preview", item.id))
            item.status = "Queued"
            job = DownloadJob(id=uuid4().hex, url=item.url, title=item.filename or item.title, mode=item.mode,
                              kind=kind_override or item.kind, quality=int(quality), folder=str(folder), start=start, end=end,
                              filename=item.filename, replace_existing=replace_existing)
            self.history.create({"id": job.id, "url": job.url, "title": job.title,
                                 "kind": job.kind, "quality": str(job.quality), "folder": job.folder,
                                 "mode": job.mode, "start_seconds": job.start, "end_seconds": job.end})
            self.cancel_flags[item.id] = asyncio.Event()
            self.stop_flags[item.id] = asyncio.Event()
            self.jobs[item.id] = job
            self.refresh_video_list()
            await self._run_download(item, job)
            return item.status
        except Exception as ex:
            item.busy = False
            self.cancel_flags.pop(item.id, None)
            self.stop_flags.pop(item.id, None)
            self.jobs.pop(item.id, None)
            item.status = "Failed"
            item.error = str(ex)
            self.notice(item.error, error=True, scope=("name", item.id) if isinstance(ex, FileExistsError) else None)
            self.refresh_video_list()
            return item.status

    async def download_all(self):
        self.cancel_shutdown_countdown()
        if not self.pending_downloads and not self.batch_dispatches and not any(i.status == "Stopped" for i in self.items.values()):
            self.cycle_results.clear()
        self.batch_dispatches += 1
        try:
            await self._download_all()
        finally:
            self.batch_dispatches -= 1
            self.maybe_shutdown()

    async def _download_all(self):
        try:
            for item in self.items.values():
                self.commit_pending_name(item)
        except (ValueError, OSError) as ex:
            self.notice(str(ex), error=True)
            return
        self._input_revision += 1
        await self._parse_input_after_delay(self._input_revision, delay=0)
        targets = [x for x in self.items.values() if not x.busy and x.status != "Completed" and can_download(x.url)]
        if not targets:
            self.notice("Paste at least one link to download.", error=True)
            return
        jobs = []
        errors = []
        for item in targets:
            try:
                cut = self.check_cut(item, notify=False)
                if cut is None:
                    errors.append((item, item.cut_error))
                    continue
                start, end = cut
                if self.batch_mode == 'shared':
                    q = self.shared_quality
                    kind = self.shared_kind
                else:
                    q = item.quality if item.quality is not None else quality_choices(item.kind, item.resolutions, item.audio_rates)[0]
                    kind = item.kind
                if kind not in available_formats(source_name(item.url) == 'SoundCloud'):
                    raise ValueError('Choose an audio format for SoundCloud items.')
                jobs.append((item, kind, q, start, end))
            except ValueError as ex:
                errors.append((item, str(ex)))
        if errors:
            first, message = errors[0]
            self.notice(message, error=True, scope=("cut", first.id) if first.cut_error else None)
            self.refresh_video_list()
            return
        folder = await self.folder_for_batch()
        if not folder:
            return

        self.notice(f"Queued {len(jobs)} downloads.")
        await asyncio.gather(*(self.download_one(item, quality, folder, kind) for item, kind, quality, _, _ in jobs))

    async def _run_download(self, item: MediaItem, job: DownloadJob):
        async with self._download_limit:
            if self.cancel_flags[item.id].is_set() or self.stop_flags[item.id].is_set():
                result = {"status": "Cancelled" if self.cancel_flags[item.id].is_set() else "Stopped",
                          "files": [], "error": "", "log": ""}
            else:
                item.status = "Connecting..."
                self.render_if_downloads()
                def progress(value, label):
                    import time
                    item.progress = value
                    if not self.cancel_flags[item.id].is_set() and not self.stop_flags[item.id].is_set():
                        item.status = label
                    now = time.monotonic()
                    if now - self._progress_last_update > 0.3 or value >= .99:
                        self._progress_last_update = now
                        self.page.run_task(self.refresh_download_cards)
                try:
                    if job.mode == "stream":
                        async with self._stream_limit:
                            result = await download(job, self.settings, progress, self.cancel_flags[item.id], self.stop_flags[item.id])
                    else:
                        result = await download(job, self.settings, progress, self.cancel_flags[item.id], self.stop_flags[item.id])
                except Exception as ex:
                    result = {"status": "Failed", "files": [], "error": str(ex), "log": str(ex)}
            job.completed_files = list(dict.fromkeys(job.completed_files + result.get("files", [])))
            result["files"] = job.completed_files
            if result["status"] != "Stopped":
                try:
                    discard_partial(job)
                except OSError as ex:
                    result["error"] = f"Temporary files could not be removed: {ex}"
            item.busy = False
            item.status = result["status"]
            if item.status == "Cancelled":
                item.progress = 0
            item.error = result.get("error") or ""
            item.log = result.get("log") or ""
            if result["status"] == "Completed":
                item.progress = 1
                files = result.get("files", [])
                item.downloaded_files = list(files)
                item.download_folder = str(Path(files[0]).parent) if files else job.folder
                if job.mode != 'playlist':
                    item.downloaded_file = next(iter(files), '')
            self.history.update(job.id, result["status"], result.get("files"), item.error, item.log)
            self.cancel_flags.pop(item.id, None)
            self.stop_flags.pop(item.id, None)
            if result["status"] != "Stopped":
                self.jobs.pop(item.id, None)
            if item.id in self.removing_items:
                self.removing_items.discard(item.id)
                self.items.pop(item.id, None)
            self.render_if_downloads()
            if result["status"] == "Completed":
                self.success_popup(f"Download complete: {item.filename or item.title}")
            elif result["status"] not in {"Cancelled", "Stopped"}:
                self.notice(f"{item.title}: {item.error}", error=True, log=item.log or item.error)

    async def refresh_download_cards(self):

        self.refresh_video_list()

    def render_if_downloads(self):
        self.refresh_video_list()

    def cancel_one(self, item: MediaItem):
        def cancel():
            self._cancel_item(item)
            self.refresh_video_list()
        self.confirm("Cancel?", "Discard download?", "Cancel", cancel)

    # History
    def toggle_history_detail(self, id_: str):
        if id_ in self.expanded_history:
            self.expanded_history.discard(id_)
        else:
            self.expanded_history.add(id_)
        self.render_history()
        self.page.update()

    def delete_history_row(self, id_: str):
        self.history.delete(id_)
        self.expanded_history.discard(id_)
        self.render_history()
        self.notice('History entry deleted. The downloaded file was not deleted.')

    def history_detail(self, r):
        try:
            files = json.loads(r['files'] or '[]')
        except (ValueError, TypeError):
            files = []
        def detail(label: str, value: str):
            return ft.Column(spacing=3, controls=[self.secondary(label, 11),
                ft.Text(value or '—', size=12, selectable=True)])
        clip = 'Full video'
        if r['start_seconds'] is not None or r['end_seconds'] is not None:
            clip = (f"{fmt_time(r['start_seconds'] or 0)} – " +
                    (fmt_time(r['end_seconds']) if r['end_seconds'] is not None else 'End'))
        content = [
            detail('Source', source_name(r['url'])),
            detail('URL', r['url']),
            detail('Started', r['created_at']),
            detail('Finished', r['finished_at'] or '—'),
            detail('Format / quality', f"{str(r['kind']).upper()}  ·  {r['quality']}"),
            detail('Mode / clip', f"{r['mode']}  ·  {clip}"),
            detail('Status', r['status']),
            detail('Destination', r['folder']),
        ]
        if files:
            content.append(detail('Downloaded files', '\n'.join(files)))
            content.append(self.button(content='Open folder', icon=ft.Icons.FOLDER_OPEN,
                on_click=lambda e, paths=tuple(files): self.open_downloaded_files(paths)))
        if r['error']:
            content.append(detail('Error', r['error']))
        if r['log'] and r['status'] not in ('Completed', 'Hoàn tất'):
            content.append(ft.TextButton(content='View error log',
               on_click=lambda e, log=r['log']: self.show_history_log(log)))
        return ft.Container(padding=ft.Padding.only(left=42, right=8, top=8, bottom=8),
            content=ft.Column(spacing=12, controls=content))

    def show_history_log(self, log: str):
        self._last_log = log
        self.show_last_error()

    def render_history(self):
        rows = self.history.rows()
        cards = []
        for r in rows:
            status = str(r['status'])
            status = {'Hoàn tất': 'Completed', 'Lỗi': 'Failed', 'Đã huỷ': 'Cancelled',
                      'Đang chờ': 'Queued', 'Cảnh báo': 'Partial'}.get(status, status)
            expanded = r['id'] in self.expanded_history
            summary = ft.Container(on_click=lambda e, key=r['id']: self.toggle_history_detail(key),
                expand=True, padding=ft.Padding.symmetric(horizontal=2, vertical=2),
                content=ft.Row(spacing=13, controls=[
                    ft.Icon(ft.Icons.CHECK_CIRCLE if status == 'Completed' else
                            ft.Icons.ERROR_OUTLINE if status == 'Failed' else ft.Icons.SCHEDULE,
                            color=GREEN if status == 'Completed' else RED if status == 'Failed' else BLUE),
                    ft.Column(expand=True, spacing=5, controls=[
                        ft.Text(r['title'] or r['url'], max_lines=1, size=14, weight=ft.FontWeight.BOLD),
                        self.secondary(f"{r['created_at']}  ·  {source_name(r['url'])}  ·  {str(r['kind']).upper()}  ·  {r['quality']}",
                                       11, max_lines=1)]),
                    ft.Text(status, size=12, color=GREEN if status == 'Completed' else
                            RED if status == 'Failed' else self.palette()[2]),
                    ft.Icon(ft.Icons.EXPAND_LESS if expanded else ft.Icons.EXPAND_MORE, size=19),
                ]))
            cards.append(self.box(ft.Column(spacing=8, controls=[
                ft.Row(controls=[summary,
                    ft.IconButton(icon=ft.Icons.CLOSE, tooltip='Delete history entry',
                        on_click=lambda e, key=r['id']: self.delete_history_row(key))]),
                *([ft.Divider(height=4, color=self.palette()[3]), self.history_detail(r)] if expanded else []),
            ]), padding=12))
        self.content.content = ft.Column(expand=True, spacing=16, controls=[
            ft.Row(controls=[ft.Text('History', size=24, weight=ft.FontWeight.BOLD),
                             ft.Container(expand=True),
                             self.button(content='Refresh', icon=ft.Icons.REFRESH,
                                       bgcolor='#FFFFFF' if self.settings.get('theme') == 'light' else '#1A2235', color=BLUE,
                                       on_click=lambda e: self.select_tab('History')),
                             self.button(content='Clear history', icon=ft.Icons.DELETE_OUTLINE,
                                       bgcolor='#FFFFFF' if self.settings.get('theme') == 'light' else '#1A2235', color=BLUE,
                                       on_click=self.clear_history_confirm)]),
            ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=10,
                      controls=cards if cards else [self.box(ft.Container(height=140,
                          alignment=ft.Alignment.CENTER,
                          content=self.secondary('No downloads yet.')))]),
        ])

    # Settings
    def set_shutdown(self, enabled):
        self.shutdown_enabled = enabled and shutdown_command() is not None
        if not self.shutdown_enabled:
            self.cancel_shutdown_countdown()
        self.page.update()

    def cancel_shutdown_countdown(self):
        if self.shutdown_task is not None:
            task = self.shutdown_task
            self.shutdown_task = None
            task.get_loop().call_soon_threadsafe(task.cancel)
        self.shutdown_cancel.visible = False

    def cancel_shutdown(self, e=None):
        self.shutdown_enabled = False
        self.cancel_shutdown_countdown()
        if self.current_tab == "Settings":
            self.select_tab("Settings")
        self.notice("Shutdown cancelled.")

    def maybe_shutdown(self):
        if (not self.shutdown_enabled or shutdown_command() is None or self.shutdown_task is not None
                or not ready_to_shutdown(self.items.values(), self.cycle_results,
                                         self.pending_downloads, self.batch_dispatches)):
            return
        self.shutdown_task = asyncio.create_task(self.shutdown_countdown())

    async def shutdown_countdown(self):
        try:
            self.shutdown_cancel.visible = True
            for remaining in range(60, 0, -1):
                if self.shutdown_task is not asyncio.current_task() or not self.shutdown_enabled:
                    return
                self.notice(f"Downloads complete. Shutting down in {remaining}s.")
                await asyncio.sleep(1)
            if (self.shutdown_task is asyncio.current_task() and self.shutdown_enabled
                    and ready_to_shutdown(self.items.values(), self.cycle_results,
                                          self.pending_downloads, self.batch_dispatches)):
                self.shutdown_enabled = False
                await asyncio.to_thread(subprocess.run, shutdown_command(), check=True, timeout=30)
        except asyncio.CancelledError:
            raise
        except Exception as ex:
            self.notice(f"Shutdown failed: {ex}", error=True)
        finally:
            if self.shutdown_task is asyncio.current_task():
                self.shutdown_task = None
                self.shutdown_cancel.visible = False
                self.page.update()

    def refresh_theme_controls(self, control):
        if control is None:
            return
        if isinstance(control, ft.Button) and control.bgcolor not in (BLUE, RED):
            control.bgcolor = self.neutral_button_bg()
            control.color = self.neutral_button_fg()
        if isinstance(control, ft.Text) and control.color in (MUTED_LIGHT, MUTED_DARK):
            control.color = self.palette()[2]
        if isinstance(control, ft.Divider):
            control.color = self.palette()[3]
        for child in getattr(control, "controls", []) or []:
            self.refresh_theme_controls(child)
        child = getattr(control, "content", None)
        if child is not None and not isinstance(child, str):
            self.refresh_theme_controls(child)

    def persist(self, key, value):
        self.settings[key] = value
        save_settings(self.settings)
        if key == "theme":
            self.apply_theme()
            self.render_navigation()
            self.refresh_theme_controls(self.content.content)
            for name, button in self._theme_buttons.items():
                button.bgcolor = BLUE if name == value else self.neutral_button_bg()
                button.color = "#FFFFFF" if name == value else self.neutral_button_fg()
            for card in self._settings_cards:
                card.bgcolor = self.palette()[1]
                card.border = ft.Border.all(1, self.palette()[3])
        elif key == "parallel_jobs":
            self._download_limit = asyncio.Semaphore(max(1, min(5, int(value))))
        self.page.update()

    async def browse_download_dir(self, e):
        folder = await ft.FilePicker().get_directory_path(dialog_title="Default download folder")
        if folder:
            self.persist("download_dir", folder)
            self.refresh_setting_path('download_dir')

    async def browse_tool_dir(self, key: str, title: str):
        folder = await ft.FilePicker().get_directory_path(dialog_title=title)
        if folder:
            self.persist(key, folder)
            self.refresh_setting_path(key)
            self.refresh_tools_status()
            if key in {'tools_dir', 'deno_dir', 'ffmpeg_dir'}:
                self.retry_failed_previews()

    def retry_failed_previews(self):
        for item in list(self.items.values()):
            if item.status in {'Preview failed', 'Preview unavailable'}:
                item.preview_ready = False
                self.page.run_task(self.fetch_preview, item)

    def clear_history_confirm(self, e):
        if any(i.busy or i.status == "Stopped" for i in self.items.values()):
            self.notice("Finish or cancel active downloads before clearing history.", error=True)
            return
        self.history.clear()
        self.select_tab("History")
        self.notice("History cleared.")

    def refresh_setting_path(self, key: str):
        control = self._setting_path_fields.get(key)
        if control is None:
            return
        value = str(self.settings.get(key, ''))
        if key in ('tools_dir', 'ffmpeg_dir', 'deno_dir') and not value:
            name = {'tools_dir': 'yt-dlp', 'ffmpeg_dir': 'ffmpeg', 'deno_dir': 'deno'}[key]
            binary = resolve_tool(name, self.settings)
            value = str(binary.parent) if binary else ''
        control.value = value
        control.update()

    def refresh_tools_status(self):
        if self._tool_status_list is not None:
            self._tool_status_list.controls = [self.tool_status(name) for name in
                ('yt-dlp', 'ffmpeg', 'ffprobe', 'deno')]
            self._tool_status_list.update()

    def setting_path(self, title: str, key: str):
        display = self.settings[key]
        if key in ('tools_dir', 'ffmpeg_dir', 'deno_dir') and not display:
            name = {'tools_dir': 'yt-dlp', 'ffmpeg_dir': 'ffmpeg', 'deno_dir': 'deno'}[key]
            binary = resolve_tool(name, self.settings)
            display = str(binary.parent) if binary else ''
        field = ft.TextField(value=display, read_only=True, expand=True,
                             hint_text='Auto-detect' if key != 'download_dir' else '', height=54)
        self._setting_path_fields[key] = field
        return ft.Column(spacing=10, controls=[
            self.secondary(title, size=12),
            ft.Row(spacing=12, controls=[
                field,
                self.button(content='Browse', on_click=(
                    (lambda e: self.page.run_task(self.browse_download_dir, e)) if key == 'download_dir'
                    else (lambda e, k=key, t=title: self.page.run_task(self.browse_tool_dir, k, t))),
                    height=46),
            ]),
        ])

    def clear_setting_path(self, key):
        self.persist(key, '')
        self.refresh_setting_path(key)
        self.refresh_tools_status()
        self.retry_failed_previews()

    def tool_status(self, name: str):
        binary = resolve_tool(name, self.settings)
        label = {'yt-dlp': 'yt-dlp', 'ffmpeg': 'FFmpeg', 'ffprobe': 'FFprobe', 'deno': 'Deno'}[name]
        if binary:
            return ft.Row(spacing=8, controls=[ft.Icon(ft.Icons.CHECK_CIRCLE, color=GREEN, size=15),
                 ft.Text(f'{label}: {binary}', selectable=True, size=11, no_wrap=False, expand=True)])
        return ft.Row(spacing=8, controls=[ft.Icon(ft.Icons.ERROR_OUTLINE, color=RED, size=15),
                                          ft.Text(f'{label}: Not found · ' + (package_manager_hint() if name in ('ffmpeg', 'ffprobe') and system() != 'Windows' else 'click Browse above to locate the folder'), size=11, color=RED)])

    def render_settings(self):
        if self.current_tab != 'Settings':
            return
        self._setting_path_fields = {}
        self._tool_status_list = ft.Column(spacing=9, controls=[self.tool_status(name)
             for name in ('yt-dlp', 'ffmpeg', 'ffprobe', 'deno')])
        self._cookie_file_field = ft.TextField(value=self.settings.get('cookies_file', ''),
             hint_text='Optional cookies.txt file', read_only=True, expand=True, height=50)
        dark_btn = self.button(content='Dark', icon=ft.Icons.DARK_MODE_OUTLINED,
             bgcolor=BLUE if self.settings['theme'] == 'dark' else None,
             color='#FFFFFF' if self.settings['theme'] == 'dark' else None,
             on_click=lambda e: self.persist('theme', 'dark'))
        light_btn = self.button(content='Light', icon=ft.Icons.LIGHT_MODE_OUTLINED,
             bgcolor=BLUE if self.settings['theme'] == 'light' else None,
             color='#FFFFFF' if self.settings['theme'] == 'light' else None,
             on_click=lambda e: self.persist('theme', 'light'))
        self._theme_buttons = {'dark': dark_btn, 'light': light_btn}
        self.content.content = ft.Column(expand=True, spacing=17, controls=[
            ft.Text('Settings', size=24, weight=ft.FontWeight.BOLD),
            ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=18, controls=[
                self.box(ft.Column(spacing=20, controls=[
                    ft.Text('Downloads', size=16, weight=ft.FontWeight.BOLD),
                    self.setting_path('Default folder', 'download_dir'),
                    ft.Row(spacing=17, controls=[
                        ft.Switch(value=self.settings['ask_folder'],
                            on_change=lambda e: self.persist('ask_folder', bool(e.control.value))),
                        ft.Column(spacing=3, expand=True, controls=[
                            ft.Text('Ask where to save', size=13),
                            self.secondary('Choose once per batch.', size=11),
                        ]),
                    ]),
                    ft.Row(spacing=12, controls=[
                        ft.Switch(value=self.shutdown_enabled, disabled=shutdown_command() is None,
                                  on_change=lambda e: self.set_shutdown(bool(e.control.value))),
                        ft.Column(expand=True, spacing=3, controls=[
                            ft.Text("Shut down computer after downloads", size=13),
                        ]),
                    ]),
                    ft.Row(wrap=True, spacing=20, run_spacing=19, controls=[
                        self.number_setting('Max file size (MB)', 'max_size_mb', 220, 0, 100000),
                        self.number_setting('Concurrent downloads', 'parallel_jobs', 220, 1, 5),
                        self.number_setting('Playlist video limit', 'playlist_max_videos', 220, 1, 10000),
                        self.number_setting('Stream limit (minutes)', 'stream_limit_minutes', 220, 1, 1440),
                    ]),
                ]), padding=23),
                self.box(ft.Column(spacing=15, controls=[
                    ft.Text('Appearance', size=16, weight=ft.FontWeight.BOLD),
                    ft.Row(spacing=14, controls=[
                        dark_btn,
                        light_btn,
                    ]),
                ]), padding=23),
                self.box(ft.Column(spacing=13, controls=[
                    ft.Text('Video playback', size=16, weight=ft.FontWeight.BOLD),
                    ft.Row(spacing=16, controls=[
                        ft.Switch(value=self.settings.get('video_preview', False),
                                  on_change=lambda e: self.set_preview_setting(bool(e.control.value))),
                        ft.Column(spacing=4, expand=True, controls=[
                            ft.Text('Enable video preview', size=13),
                            self.secondary('Adds Play buttons. Playback requires a compatible video stream.', size=11),
                        ]),
                    ]),
                ]), padding=23),
                self.box(ft.Column(spacing=17, controls=[
                    ft.Text('Tools & updates', size=16, weight=ft.FontWeight.BOLD),
                    ft.Row(controls=[ft.Switch(value=self.settings.get("check_updates", True),
                        on_change=lambda e: self.persist("check_updates", bool(e.control.value))),
                        ft.Text("Check for updates on startup", expand=True)]),
                    ft.TextButton(content="Check now", icon=ft.Icons.REFRESH,
                        on_click=lambda e: self.page.run_task(self.auto_check_updates)),
                    self.secondary("Updates are installed only after you click Update.", 11),
                    self.setting_path('Tools folder', 'tools_dir'),
                    self.setting_path('FFmpeg folder', 'ffmpeg_dir'),
                    self.setting_path('Deno folder', 'deno_dir'),
                    self._tool_status_list,
                    ft.Divider(height=8, color=self.palette()[3]),
                    ft.Text('Browser session (optional)', size=13, weight=ft.FontWeight.BOLD),
                    self.secondary('Off by default. Public videos do not need browser cookies.', 11),
                    ft.Row(spacing=12, controls=[
                        ft.Switch(value=self.settings.get('use_browser_cookies', False),
                                  on_change=lambda e: self.persist('use_browser_cookies', bool(e.control.value))),
                        ft.Text('Use browser cookies for restricted videos', size=12),
                    ]),
                    ft.Dropdown(width=230, value=self.settings.get('cookies_browser', 'none'),
                        options=[ft.DropdownOption(key=v, text=t) for v, t in
                                 [('none','Off'), ('chrome','Chrome'), ('edge','Edge'),
                                  ('firefox','Firefox'), ('brave','Brave')]],
                        on_select=lambda e: self.change_browser_session(e.control.value)),
                    self.secondary('If Chrome is open, the browser may lock its cookie database. Switch off, close Chrome, or use a Netscape cookies.txt file.', 11),
                    ft.Row(spacing=12, controls=[
                        self._cookie_file_field,
                        self.button(content='Browse file', on_click=lambda e: self.page.run_task(self.browse_cookie_file)),
                        self.button(content='Clear', on_click=lambda e: self.clear_cookie_file()),
                    ]),
                    ft.Divider(height=8, color=self.palette()[3]),
                    ft.Column(spacing=8, controls=[self.secondary('App update feed (HTTPS)', size=12),
                        ft.TextField(value=self.settings['app_update_manifest'],
                            hint_text='Default: GitHub Releases', height=54,
                            on_blur=lambda e: self.persist('app_update_manifest', e.control.value))]),
                ]), padding=23),
            ]),
        ])
        self._settings_cards = list(self.content.content.controls[1].controls)

    async def browse_cookie_file(self):
        files = await ft.FilePicker().pick_files(allow_multiple=False,
            file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=['txt'],
            dialog_title='Select Netscape cookies.txt')
        if files and files[0].path:
            self.persist('cookies_file', files[0].path)
            if self._cookie_file_field is not None:
                self._cookie_file_field.value = files[0].path
                self._cookie_file_field.update()

    def clear_cookie_file(self):
        self.persist('cookies_file', '')
        if self._cookie_file_field is not None:
            self._cookie_file_field.value = ''
            self._cookie_file_field.update()

    def change_browser_session(self, browser: str):
        self.persist('cookies_browser', browser)
        self.retry_failed_previews()
        self.notice('Browser selected. Enable the browser-cookie switch above only when needed.')

    def set_preview_setting(self, enabled: bool):
        self.persist('video_preview', enabled)

    def number_setting(self, label: str, key: str, width: int, min_value: int, max_value: int):
        def changed(e):
            try:
                if key == "parallel_jobs" and any(i.busy for i in self.items.values()):
                    e.control.value = str(self.settings[key])
                    e.control.update()
                    self.notice("Stop active downloads before changing concurrency.", error=True)
                    return
                value = int(e.control.value)
                if not (min_value <= value <= max_value):
                    raise ValueError
                self.persist(key, value)
                self.clear_notice(("setting", key))
            except (TypeError, ValueError):
                self.notice(f'{label}: enter {min_value}–{max_value}.', error=True, scope=("setting", key))
        return ft.Column(width=width, spacing=8, controls=[
            self.secondary(label, size=12),
            ft.TextField(value=str(self.settings[key]), height=54,
                         keyboard_type=ft.KeyboardType.NUMBER, on_blur=changed),
        ])

    # Updates
    async def auto_check_updates(self):
        if self.checking_updates or self.update_busy:
            return
        self.checking_updates = True
        try:
            await self._check_updates()
        finally:
            self.checking_updates = False

    async def _check_updates(self):

        try:
            state = await asyncio.to_thread(check_ytdlp_update)
            self.pending_ytdlp = state["needs_update"]
        except Exception as ex:
            # Missing tools remain installable even when the check fails.
            try:
                cli_exe()
            except RuntimeError:
                self.pending_ytdlp = True
                self.notice(f"yt-dlp unavailable: {ex}", error=True)
        # Check tools independently.
        results = await asyncio.gather(asyncio.to_thread(check_deno),
                                       asyncio.to_thread(check_ffmpeg), return_exceptions=True)
        for name, data in zip(('deno', 'ffmpeg'), results):
            if isinstance(data, BaseException):
                self._tools_check_errors[name] = str(data)
            elif data.get('needs_update'):
                self.pending_tools[name] = data
            else:
                self.pending_tools.pop(name, None)
        try:
            self.pending_app_update = await asyncio.to_thread(
                check_app_update, self.settings.get("app_update_manifest", ""))
        except Exception as ex:
            self.notice(f"App update check: {ex}", error=True)
        self.refresh_update_button()

    def refresh_update_button(self):
        self.update_button.visible = bool(self.pending_ytdlp or self.pending_tools or self.pending_app_update) and not self.update_busy
        requested = (["yt-dlp"] if self.pending_ytdlp else []) + [x.upper() if x == 'deno' else 'FFmpeg'
                                                               for x in self.pending_tools]
        self.update_button.content = ("Update " + ", ".join(requested)) if requested else (
            f"Update app · v{self.pending_app_update['version']}" if self.pending_app_update else "Update")
        self.page.update()

    async def confirm_tool_update(self, name: str, info: dict):
        self.page.pop_dialog()
        if self.update_busy:
            return
        self.update_busy = True
        self.refresh_update_button()
        try:
            self.notice(f'Downloading verified {name} archive...')
            message = await asyncio.to_thread(install_tool, info)
            self.pending_tools.pop(name, None)
            self.notice(message)
        except Exception as ex:
            self.notice(f'{name} update failed: {ex}', error=True)
        finally:
            self.update_busy = False
            self.refresh_update_button()

    async def apply_updates(self):
        if self.update_busy:
            return
        self.update_busy = True
        self.refresh_update_button()
        try:
            if self.pending_ytdlp:
                self.notice("Installing yt-dlp...")
                def progress(pct):
                    self.footer_text.value = f"Updating yt-dlp · {pct}%"
                    self.page.schedule_update()
                version = await asyncio.to_thread(install_ytdlp, progress)
                self.pending_ytdlp = False
                self.notice(f"yt-dlp {version} installed.")
                # Retry preview for cards that could not be read without yt-dlp.
                for item in self.items.values():
                    if item.status in {"Preview failed", "Preview unavailable"}:
                        item.preview_ready = False
                        self.page.run_task(self.fetch_preview, item)
            elif self.pending_tools:
                name, info = next(iter(self.pending_tools.items()))
                if name == 'ffmpeg':
                    # The stable Windows FFmpeg archive is large; ask before downloading.
                    self.page.show_dialog(ft.AlertDialog(
                        title=ft.Text('Update FFmpeg?'),
                        content=ft.Text('This download may exceed 180 MB. The archive is verified with SHA256. Existing custom FFmpeg paths will remain unchanged.'),
                        actions=[ft.TextButton(content='Cancel', on_click=lambda e: self.page.pop_dialog()),
                                 self.button(content='Download and install', bgcolor=BLUE, color='#FFFFFF',
                                           on_click=lambda e: self.page.run_task(self.confirm_tool_update, name, info))]))
                else:
                    self.notice(f'Updating {name}...')
                    message = await asyncio.to_thread(install_tool, info)
                    self.pending_tools.pop(name, None)
                    self.notice(message)
            elif self.pending_app_update:
                update = self.pending_app_update
                self.notice("Downloading verified app update...")
                path = await asyncio.to_thread(stage_app_update, update)
                self.pending_app_update = None
                self.page.show_dialog(ft.AlertDialog(title=ft.Text("Update downloaded"),
                    content=ft.Text(f"Installer saved: {path}\nClose Vocaflop before installing the downloaded update."),
                    actions=[self.button(content="Close", on_click=lambda e: self.page.pop_dialog())]))
        except Exception as ex:
            self.notice(f"Update failed: {ex}", error=True)
        finally:
            self.update_busy = False
            self.refresh_update_button()


def main(page: ft.Page):
    VocaflopUI(page)
