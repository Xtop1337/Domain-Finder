"""app.py — Flet GUI for domain_finder.

Run with: python app.py
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import flet as ft

from core import RESULTS_DIR, search, save_json


LEVEL_COLORS = {
    "info":  ft.Colors.BLUE_400,
    "ok":    ft.Colors.GREEN_400,
    "warn":  ft.Colors.AMBER_400,
    "error": ft.Colors.RED_400,
}


def main(page: ft.Page) -> None:
    page.title = "Domain Finder"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 16
    page.window.width = 980
    page.window.height = 700
    page.window.min_width = 820
    page.window.min_height = 580

    input_field: ft.TextField
    progress_bar: ft.ProgressBar
    progress_label: ft.Text
    domains_list: ft.ListView
    logs_list: ft.ListView
    found_counter: ft.Text
    cb_crtsh: ft.Checkbox
    cb_hackertarget: ft.Checkbox
    find_button: ft.ElevatedButton
    theme_button: ft.IconButton
    save_button: ft.OutlinedButton
    copy_button: ft.OutlinedButton
    clear_button: ft.OutlinedButton

    last_payload: dict | None = None
    is_searching = False

    def append_log(message: str, level: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        color = LEVEL_COLORS.get(level, ft.Colors.GREY_400)
        logs_list.controls.append(
            ft.Row(
                controls=[
                    ft.Text(ts, size=11, color=ft.Colors.GREY_500, width=70),
                    ft.Text(
                        message,
                        size=12,
                        color=color,
                        selectable=True,
                        expand=True,
                    ),
                ],
                spacing=8,
            )
        )
        logs_list.update()

    def set_progress(pct: int) -> None:
        try:
            value = max(0, min(100, pct)) / 100.0
        except (TypeError, ValueError):
            return
        progress_bar.value = value
        if pct < 0:
            progress_label.value = ""
        else:
            progress_label.value = f"{max(0, min(100, pct))}%"
        progress_bar.update()
        progress_label.update()

    def reset_ui() -> None:
        domains_list.controls.clear()
        logs_list.controls.clear()
        found_counter.value = "Найдено: 0"
        set_progress(0)
        page.update()

    def toggle_theme(_=None) -> None:
        if page.theme_mode == ft.ThemeMode.DARK:
            page.theme_mode = ft.ThemeMode.LIGHT
            theme_button.icon = ft.Icons.DARK_MODE
        else:
            page.theme_mode = ft.ThemeMode.DARK
            theme_button.icon = ft.Icons.LIGHT_MODE
        page.update()

    def on_progress(message: str, level: str, pct: int) -> None:
        append_log(message, level)
        if pct >= 0:
            set_progress(pct)

    async def run_search(_=None) -> None:
        nonlocal last_payload, is_searching

        if is_searching:
            return

        keyword = (input_field.value or "").strip()
        if not keyword:
            append_log("Введите ключевое слово или домен.", "warn")
            return

        sources: list[str] = []
        if cb_crtsh.value:
            sources.append("crt.sh")
        if cb_hackertarget.value:
            sources.append("hackertarget")
        if not sources:
            append_log("Выберите хотя бы один источник.", "warn")
            return

        is_searching = True
        find_button.disabled = True
        input_field.disabled = True
        cb_crtsh.disabled = True
        cb_hackertarget.disabled = True
        save_button.disabled = True
        copy_button.disabled = True
        reset_ui()
        append_log(f"Старт поиска для '{keyword}' (источники: {', '.join(sources)})", "info")
        page.update()

        try:
            payload = await asyncio.to_thread(search, keyword, sources, on_progress)
        except Exception as exc:
            append_log(f"Ошибка выполнения: {exc}", "error")
            payload = None
        finally:
            is_searching = False
            find_button.disabled = False
            input_field.disabled = False
            cb_crtsh.disabled = False
            cb_hackertarget.disabled = False

        if payload is None:
            page.update()
            return

        last_payload = payload

        for entry in payload.get("domains", []):
            d = entry["domain"]
            sources_tag = ", ".join(entry.get("sources", []))
            domains_list.controls.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.LANGUAGE, size=14, color=ft.Colors.CYAN_300),
                            ft.Text(
                                d,
                                size=13,
                                weight=ft.FontWeight.W_500,
                                selectable=True,
                                expand=True,
                            ),
                            ft.Text(
                                sources_tag,
                                size=10,
                                color=ft.Colors.GREY_500,
                            ),
                        ],
                        spacing=8,
                    ),
                    padding=ft.Padding(left=8, right=8, top=4, bottom=4),
                    border_radius=4,
                )
            )

        found_counter.value = f"Найдено: {payload['total_unique']}"
        save_button.disabled = payload["total_unique"] == 0
        copy_button.disabled = payload["total_unique"] == 0
        page.update()

    def copy_all(_=None) -> None:
        if not last_payload:
            return
        text = "\n".join(e["domain"] for e in last_payload.get("domains", []))
        page.set_clipboard(text)
        append_log(f"Скопировано {last_payload['total_unique']} доменов в буфер.", "ok")
        page.show_dialog(
            ft.SnackBar(content=ft.Text("Скопировано в буфер обмена"), open=True)
        )
        page.update()

    def save_to_file(_=None) -> None:
        if not last_payload:
            return
        try:
            path = save_json(last_payload["keyword"], last_payload)
            append_log(f"Сохранено: {path}", "ok")
            page.show_dialog(
                ft.SnackBar(content=ft.Text(f"Сохранено: {path.name}"), open=True)
            )
        except OSError as exc:
            append_log(f"Не удалось сохранить: {exc}", "error")
        page.update()

    def clear_all(_=None) -> None:
        nonlocal last_payload
        last_payload = None
        input_field.value = ""
        save_button.disabled = True
        copy_button.disabled = True
        reset_ui()
        append_log("Очищено.", "info")
        page.update()

    def on_submit(_=None) -> None:
        page.run_task(run_search)

    # ── Build UI ──────────────────────────────────────────────────────────
    input_field = ft.TextField(
        label="Ключевое слово или домен",
        hint_text="osu, steam, discord, youtube.com, ...",
        expand=True,
        on_submit=on_submit,
        autofocus=True,
    )

    find_button = ft.ElevatedButton(
        "Найти",
        icon=ft.Icons.SEARCH,
        on_click=on_submit,
    )

    cb_crtsh = ft.Checkbox(label="crt.sh", value=True)
    cb_hackertarget = ft.Checkbox(label="HackerTarget", value=True)

    sources_row = ft.Row(
        controls=[
            ft.Text("Источники:", size=12, weight=ft.FontWeight.BOLD),
            cb_crtsh,
            cb_hackertarget,
        ],
        spacing=12,
    )

    progress_bar = ft.ProgressBar(width=920, value=0)
    progress_label = ft.Text("", size=11, color=ft.Colors.GREY_500)

    progress_row = ft.Row(
        controls=[progress_bar, progress_label],
        spacing=8,
        alignment=ft.MainAxisAlignment.START,
    )

    found_counter = ft.Text("Найдено: 0", size=13, weight=ft.FontWeight.BOLD)

    domains_list = ft.ListView(
        expand=True,
        spacing=2,
        padding=ft.Padding(left=4, right=4, top=4, bottom=4),
    )
    logs_list = ft.ListView(
        expand=True,
        spacing=2,
        padding=ft.Padding(left=4, right=4, top=4, bottom=4),
    )

    domain_pane = ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[found_counter],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(height=8, thickness=1),
                domains_list,
            ],
            expand=True,
            spacing=4,
        ),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.2, ft.Colors.GREY)),
        border_radius=8,
        padding=8,
        expand=True,
    )

    log_pane = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text("Логи", size=13, weight=ft.FontWeight.BOLD),
                ft.Divider(height=8, thickness=1),
                logs_list,
            ],
            expand=True,
            spacing=4,
        ),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.2, ft.Colors.GREY)),
        border_radius=8,
        padding=8,
        expand=True,
    )

    copy_button = ft.OutlinedButton(
        "Копировать всё",
        icon=ft.Icons.COPY,
        on_click=copy_all,
        disabled=True,
    )
    save_button = ft.OutlinedButton(
        "Сохранить JSON",
        icon=ft.Icons.SAVE,
        on_click=save_to_file,
        disabled=True,
    )
    clear_button = ft.OutlinedButton(
        "Очистить",
        icon=ft.Icons.CLEAR,
        on_click=clear_all,
    )

    theme_button = ft.IconButton(
        icon=ft.Icons.LIGHT_MODE,
        tooltip="Переключить тему",
        on_click=toggle_theme,
    )

    page.add(
        ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("Domain Finder", size=22, weight=ft.FontWeight.BOLD),
                        ft.Container(expand=True),
                        theme_button,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Row(
                    controls=[input_field, find_button],
                    spacing=8,
                ),
                sources_row,
                progress_row,
                ft.ResponsiveRow(
                    controls=[
                        ft.Container(domain_pane, col={"sm": 12, "md": 7}),
                        ft.Container(log_pane,    col={"sm": 12, "md": 5}),
                    ],
                    expand=True,
                    run_spacing=12,
                ),
                ft.Row(
                    controls=[copy_button, save_button, clear_button],
                    spacing=8,
                    alignment=ft.MainAxisAlignment.END,
                ),
            ],
            expand=True,
            spacing=10,
        )
    )

    append_log("Готов к работе. Введите ключевое слово и нажмите 'Найти'.", "info")


if __name__ == "__main__":
    ft.app(target=main)
