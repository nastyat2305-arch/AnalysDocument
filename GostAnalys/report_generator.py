import json
from rich.console import Console


console = Console()


def format_console_report(filename: str, doc_type: str, res_trts: dict, res_mr23: dict) -> str:
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
            if len(contras) > 3: lines.append(f"    ... и ещё {len(contras) - 3}")
        else:
            lines.append("  [green]✅ Логические противоречия: не обнаружены[/]")

        # Разрывы
        gaps = res.get("gaps", [])
        if gaps:
            lines.append(f"  [bold yellow]⚪ Смысловые разрывы ({len(gaps)}):[/]")
            for g in gaps[:3]:
                lines.append(f"    • В эталоне требуется: {g.get('ref_req', '-')[:120]}")
                lines.append(f"      В документе: {g.get('missing_context', 'отсутствует')}")
            if len(gaps) > 3: lines.append(f"    ... и ещё {len(gaps) - 3}")
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


def save_report(reports: list, path: str, fmt: str = "json"):
    import os
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if fmt == "json":
        with open(path, "w", encoding="utf-8") as f:
            json.dump(reports, f, ensure_ascii=False, indent=2)
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(reports))
    console.print(f"\n💾 Отчёт сохранён: [cyan]{path}[/]")
