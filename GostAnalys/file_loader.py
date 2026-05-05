from pathlib import Path




def load_document(filepath: str) -> str:
    """Загружает текст из .txt файла."""
    p = Path(filepath)
    if not p.exists():
        raise FileNotFoundError(f"Файл не найден: {filepath}")

    ext = p.suffix.lower()
    if ext != '.txt':
        raise ValueError("Поддерживается только формат .txt")
    
    try:
        return p.read_text(encoding='utf-8-sig')
    except Exception as e:
        raise RuntimeError(f"Ошибка чтения {filepath}: {e}")


def detect_document_type(filename: str, text: str = None) -> str:
    """Определяет тип документа по имени или заголовку."""
    name = filename.upper()
    type_map = {'ТТК': 'ТТК', 'ТУ': 'ТУ', 'ТК': 'ТК', 'ТИ': 'ТИ', 'МУК': 'МУК', 'МУ': 'МУ', 'ГОСТ': 'ГОСТ', 'Р': 'Р'}
    for k, v in type_map.items():
        if k in name:
            return v

    if text:
        t = text[:600].upper()
        if 'ТЕХНИЧЕСКИЕ УСЛОВИЯ' in t: return 'ТУ'
        if 'ТЕХНОЛОГИЧЕСКАЯ КАРТА' in t: return 'ТК'
        if 'ТЕХНОЛОГИЧЕСКАЯ ИНСТРУКЦИЯ' in t: return 'ТИ'
        if 'МЕТОДИЧЕСКИЕ' in t: return 'МУ'
    return 'OTHER'
