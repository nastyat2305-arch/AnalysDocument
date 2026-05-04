import json
import logging
import re
from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)


def _strip_rich_markup(text: str) -> str:
    """Удаляет Rich маркировку ([...]) из текста."""
    return re.sub(r'\[/?[^\]]*\]', '', text)


def format_console_report(filename: str, doc_type: str, res_trts: dict, res_mr23: dict) -> str:
    """Форматирует отчёт для вывода в консоль с Rich маркировкой."""
    lines = []
    lines.append(f"\n[bold cyan]📄 Документ: {filename}[/] (тип: {doc_type})")

    for name, res in [("ТР ТС 21", res_trts), ("МР 2.3", res_mr23)]:
        lines.append(f"\n[bold]🔍 Сравнение с {name}:[/]")

        # Противоречия
        contras = res.get("contradictions", [])
        if contras:
            lines.append(f"  [bold red]🔴 Логические противоречия ({len(contras)}):[/]")
            for c in contras[:3]:
                lines.append(f"    • {c.get('reason', 'Несоответствие')}")
                lines.append(f"      Эталон: {c.get('ref', '-')[:100]}")
                lines.append(f"      Документ: {c.get('doc', '-')[:100]}")
            if len(contras) > 3:
                lines.append(f"    ... и ещё {len(contras) - 3}")
        else:
            lines.append("  [green]✅ Логические противоречия: не обнаружены[/]")

        # Разрывы
        gaps = res.get("gaps", [])
        if gaps:
            lines.append(f"  [bold yellow]⚪ Смысловые разрывы ({len(gaps)}):[/]")
            for g in gaps[:3]:
                lines.append(f"    • В эталоне требуется: {g.get('ref_req', '-')[:120]}")
                lines.append(f"      В документе: {g.get('missing_context', 'отсутствует')}")
            if len(gaps) > 3:
                lines.append(f"    ... и ещё {len(gaps) - 3}")
        else:
            lines.append("  [green]✅ Смысловые разрывы: не обнаружены[/]")

        # Структура
        struct = res.get("structure_issues", [])
        if struct:
            lines.append(f"  [bold magenta]📐 Структурные различия:[/]")
            for s in struct:
                lines.append(f"    • Раздел \"{s.get('section')}\" — {s.get('status')}")
        else:
            lines.append("  [green]✅ Структура соответствует[/]")

    total = len(res_trts.get("contradictions", [])) + len(res_trts.get("gaps", [])) + \
            len(res_mr23.get("contradictions", [])) + len(res_mr23.get("gaps", []))
    status = "[bold red]🚨 ОБНАРУЖЕНЫ КРИТИЧЕСКИЕ НЕСООТВЕТСТВИЯ[/]" if total > 0 else "[bold green]✨ Разрывов не обнаружено[/]"
    lines.append(f"\n{status}")
    return "\n".join(lines)


def format_txt_report(reports: list) -> str:
    """Преобразует список отчётов в текстовый формат без Rich маркировки."""
    lines = []
    lines.append("=" * 80)
    lines.append("ОТЧЁТ АНАЛИЗА ДОКУМЕНТОВ")
    lines.append(f"Всего документов: {len(reports)}")
    lines.append("=" * 80)

    for report in reports:
        filename = report.get("filename", "Неизвестный файл")
        doc_type = report.get("type", "OTHER")
        
        lines.append(f"\n{'─' * 80}")
        lines.append(f"ДОКУМЕНТ: {filename} (тип: {doc_type})")
        lines.append(f"{'─' * 80}")

        for standard, res in [("ТР ТС 21", report.get("trts", {})), ("МР 2.3", report.get("mr23", {}))]:
            lines.append(f"\n📋 Сравнение с {standard}:")
            
            # Противоречия
            contras = res.get("contradictions", [])
            if contras:
                lines.append(f"\n  🔴 ЛОГИЧЕСКИЕ ПРОТИВОРЕЧИЯ ({len(contras)}):")
                for i, c in enumerate(contras, 1):
                    lines.append(f"    {i}. Причина: {c.get('reason', 'Несоответствие')}")
                    lines.append(f"       Эталон: {c.get('ref', '-')[:150]}")
                    lines.append(f"       Документ: {c.get('doc', '-')[:150]}")
            else:
                lines.append(f"\n  ✅ Логические противоречия: не обнаружены")

            # Разрывы
            gaps = res.get("gaps", [])
            if gaps:
                lines.append(f"\n  ⚪ СМЫСЛОВЫЕ РАЗРЫВЫ ({len(gaps)}):")
                for i, g in enumerate(gaps, 1):
                    lines.append(f"    {i}. В эталоне требуется: {g.get('ref_req', '-')[:150]}")
                    lines.append(f"       В документе: {g.get('missing_context', 'отсутствует')}")
            else:
                lines.append(f"\n  ✅ Смысловые разрывы: не обнаружены")

            # Структура
            struct = res.get("structure_issues", [])
            if struct:
                lines.append(f"\n  📐 СТРУКТУРНЫЕ РАЗЛИЧИЯ:")
                for s in struct:
                    lines.append(f"    • Раздел '{s.get('section')}': {s.get('status')}")
                    if s.get('details'):
                        lines.append(f"      Подробно: {s.get('details')}")
            else:
                lines.append(f"\n  ✅ Структура соответствует")

    lines.append(f"\n{'=' * 80}")
    lines.append("КОНЕЦ ОТЧЁТА")
    lines.append(f"{'=' * 80}")

    return "\n".join(lines)


def save_report(reports: list, path: str, fmt: str = "json"):
    """Сохраняет отчёт в файл в указанном формате."""
    import os
    
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        
        if fmt == "json":
            with open(path, "w", encoding="utf-8") as f:
                json.dump(reports, f, ensure_ascii=False, indent=2)
            logger.info(f"JSON отчёт сохранён: {path}")
        elif fmt == "txt":
            # ИСПРАВЛЕНИЕ: Используем функцию для преобразования в текст вместо join
            txt_content = format_txt_report(reports)
            with open(path, "w", encoding="utf-8") as f:
                f.write(txt_content)
            logger.info(f"TXT отчёт сохранён: {path}")
        else:
            console.print(f"[red]❌ Неизвестный формат: {fmt}[/]")
            logger.error(f"Неизвестный формат отчёта: {fmt}")
            return
        
        console.print(f"\n💾 Отчёт сохранён: [cyan]{path}[/]")
    except Exception as e:
        console.print(f"[red]❌ Ошибка при сохранении отчёта: {e}[/]")
        logger.error(f"Ошибка при сохранении отчёта: {e}")
