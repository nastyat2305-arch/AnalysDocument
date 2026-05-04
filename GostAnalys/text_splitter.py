import re


def split_into_chunks(text: str, chunk_size: int = 800, overlap: int = 100) -> list:
    """Разбивает текст на перекрывающиеся смысловые блоки."""
    # Сначала делим на абзацы
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    chunks = []
    current = ""

    for p in paragraphs:
        if len(current) + len(p) > chunk_size and current:
            chunks.append(current)
            # Сохраняем хвост для перекрытия контекста
            overlap_text = " ".join(current.split()[-overlap // 4:]) if len(current.split()) > overlap // 4 else ""
            current = overlap_text + " " + p
        else:
            current += (" " if current else "") + p

    if current.strip():
        chunks.append(current.strip())
    return [c for c in chunks if len(c) > 50]
