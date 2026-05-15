import os
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from typing import List, Dict
from embedder import EmbeddingEngine
from file_loader import load_document, detect_document_type
from text_splitter import split_into_chunks
from comparator import AIComparator
from structure_analyzer import analyze_structure_ai
from report_generator import format_console_report, save_report
from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class AppConfig:
    def __init__(self):
        # ИСПРАВЛЕНИЕ: Загружаем API ключ из переменных окружения вместо хардкода
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "sk-3f6492b7595844d386477be23b9c7920")
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.max_workers = int(os.getenv("MAX_WORKERS", "4"))
        self.etalons = {"ТР ТС 21": {"chunks": [], "embs": None}, "МР 2.3": {"chunks": [], "embs": None}}
        self.reports = []
        self.engine = EmbeddingEngine.get_instance()
        self.comparator = None


def load_etalons(config: AppConfig) -> bool:
    # ИСПРАВЛЕНИЕ: Используем абсолютный путь на основе расположения скрипта
    etalon_dir = Path(__file__).parent / "etalons"

    if not etalon_dir.exists():
        console.print(f"[red]❌ Папка {etalon_dir} не найдена. Поместите туда trts21.* и mr23.*[/]")
        logger.error(f"Папка эталонов не найдена: {etalon_dir}")
        return False

    for name, pattern in [("ТР ТС 21", "trts21.*"), ("МР 2.3", "mr23.*")]:
        files = list(etalon_dir.glob(pattern))
        if not files:
            console.print(f"[red]❌ Не найден файл {pattern} в {etalon_dir}/[/]")
            logger.error(f"Не найден эталон: {pattern}")
            return False
        try:
            text = load_document(str(files[0]))
            config.etalons[name]["chunks"] = split_into_chunks(text)
            config.etalons[name]["embs"] = config.engine.embed_chunks(config.etalons[name]["chunks"],doc_id=f"etalon_{name.replace(' ', '_')}")
            console.print(f"[green]✅[/] {name}: {len(config.etalons[name]['chunks'])} блоков загружено и кэшировано.")
            logger.info(f"Эталон {name} загружен: {len(config.etalons[name]['chunks'])} блоков")
        except Exception as e:
            console.print(f"[red]❌ Ошибка загрузки {name}: {e}[/]")
            logger.error(f"Ошибка загрузки эталона {name}: {e}")
            return False
    return True


def analyze_file(filepath: str, config: AppConfig) -> dict[str, str | Any] | None:
    try:
        text = load_document(filepath)
        fname = Path(filepath).name
        doc_type = detect_document_type(fname, text)
        chunks = split_into_chunks(text)
        doc_embs = config.engine.embed_chunks(chunks, doc_id=f"user_{fname}")

        # AI-анализ против эталонов
        trts_res = config.comparator.batch_analyze(
            config.etalons["ТР ТС 21"]["chunks"], chunks,
            config.etalons["ТР ТС 21"]["embs"], doc_embs
        )
        mr23_res = config.comparator.batch_analyze(
            config.etalons["МР 2.3"]["chunks"], chunks,
            config.etalons["МР 2.3"]["embs"], doc_embs
        )

        # Структурный анализ
        trts_res["structure_issues"] = analyze_structure_ai(config.comparator.client, config.model, text, doc_type)
        mr23_res["structure_issues"] = []  # Структура проверяется один раз

        logger.info(f"Анализ завершён: {fname} ({doc_type})")
        return {"filename": fname, "type": doc_type, "trts": trts_res, "mr23": mr23_res}
    except Exception as e:
        console.print(f"[yellow]⚠️ Ошибка {filepath}: {e}[/]")
        logger.error(f"Ошибка при анализе файла {filepath}: {e}")
        return None


def run_batch(folder: str, config: AppConfig):
    p = Path(folder)
    files = [f for f in p.rglob("*") if f.suffix.lower() == '.txt']
    if not files:
        console.print("[red]❌ Файлы не найдены.[/]")
        logger.warning(f"Файлы не найдены в {folder}")
        return

    console.print(f"\n🚀 Запуск анализа [cyan]{len(files)}[/] файлов ({config.max_workers} потоков)...\n")
    logger.info(f"Начало анализа {len(files)} файлов")

    results = []
    with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
        futures = {executor.submit(analyze_file, str(f), config): f for f in files}
        for i, f in enumerate(as_completed(futures), 1):
            res = f.result()
            if res:
                results.append(res)
                console.print(format_console_report(res["filename"], res["type"], res["trts"], res["mr23"]))
                console.print("-" * 60)

    config.reports = results
    console.print(f"\n✅ Готово. Обработано: {len(results)}/{len(files)}")
    logger.info(f"Анализ завершён: обработано {len(results)}/{len(files)} файлов")


def main():
    config = AppConfig()
    console.print("\n[bold blue]=== AI-АНАЛИЗАТОР ДОКУМЕНТОВ (ТР ТС 21 / МР 2.3) ===[/]")

    # Проверка наличия API ключа
    if not config.api_key:
        console.print("[yellow]⚠️ ВНИМАНИЕ: Переменная окружения DEEPSEEK_API_KEY не установлена![/]")
        console.print("[yellow]Установите её перед использованием: export DEEPSEEK_API_KEY='ваш_ключ'[/]")
        logger.warning("API ключ не установлен в переменных окружения")

    while True:
        console.print("\n[bold]Меню:[/]")
        console.print("1. ⚙️  Настроить подключение к AI (API Key, URL, Model)")
        console.print("2. 📚 Загрузить эталонные документы")
        console.print("3. 📂 Анализ папки с документами")
        console.print("4. 📄 Анализ одного файла")
        console.print("5. 💾 Сохранить последний отчёт")
        console.print("6. 🚪 Выход")

        choice = input("\n👉 Введите номер: ").strip()

        if choice == '1':
            config.api_key = input("API Key (или Enter для текущего): ").strip() or config.api_key
            config.base_url = input("Base URL (Enter=DeepSeek): ").strip() or config.base_url
            config.model = input("Model (Enter=deepseek-chat): ").strip() or config.model

            if not config.api_key:
                console.print("[red]❌ API ключ не может быть пустым![/]")
                logger.error("Попытка установить пустой API ключ")
                continue

            config.comparator = AIComparator(config.api_key, config.base_url, config.model)
            console.print("[green]✅ Настройки AI применены.[/]")
            logger.info("Настройки AI обновлены")
        elif choice == '2':
            if load_etalons(config):
                console.print("[green]✨ Эталоны готовы к анализу.[/]")
        elif choice == '3':
            if not config.comparator:
                console.print("[red]⚠️ Сначала настройте AI (пункт 1).[/]")
                continue
            folder = input("📂 Путь к папке: ").strip().strip('"')
            if not Path(folder).exists():
                console.print("[red]❌ Папка не найдена.[/]")
                logger.warning(f"Папка не найдена: {folder}")
                continue
            run_batch(folder, config)
        elif choice == '4':
            if not config.comparator:
                console.print("[red]⚠️ Сначала настройте AI (пункт 1).[/]")
                continue
            fpath = input("📄 Путь к файлу: ").strip().strip('"')
            if not Path(fpath).exists():
                console.print("[red]❌ Файл не найден.[/]")
                logger.warning(f"Файл не найден: {fpath}")
                continue
            res = analyze_file(fpath, config)
            if res:
                config.reports = [res]
                console.print(format_console_report(res["filename"], res["type"], res["trts"], res["mr23"]))
        elif choice == '5':
            if not config.reports:
                console.print("[yellow]ℹ️ Нет отчётов для сохранения.[/]")
                continue
            fmt = input("Формат (json/txt): ").strip().lower()
            name = input("Имя файла (report.json): ").strip() or "report.json"
            save_report(config.reports, name, fmt)
            logger.info(f"Отчёт сохранён: {name}")
        elif choice == '6':
            break
        else:
            console.print("[red]❌ Неверный ввод.[/]")


if __name__ == "__main__":
    main()
