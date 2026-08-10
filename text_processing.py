"""Text normalization and chunking for speech synthesis.

The cleaning pipeline deliberately separates markup removal from whitespace
reflow. This keeps semantic content (especially numbers and percentages) intact
while turning presentation-only structure into TTS-friendly paragraphs.
"""

from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser

import emoji


_BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "dd",
    "details",
    "div",
    "dl",
    "dt",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "summary",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "ul",
}
_IGNORED_TAGS = {"script", "style", "noscript", "svg"}
_TERMINAL_PUNCTUATION = ("。", "！", "？", "!", "?", ";", "；", ".")
_TRAILING_URL_PUNCTUATION = ".,!?;:，。！？；：、)]}）】》」』"


class _PlainTextHTMLParser(HTMLParser):
    """Extract visible text and retain block boundaries from HTML fragments."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def _paragraph_break(self) -> None:
        self.parts.append("\n\n")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self._ignored_depth:
            self._ignored_depth += 1
            return
        if tag in _IGNORED_TAGS:
            self._ignored_depth = 1
        elif tag == "br":
            self.parts.append("\n")
        elif tag in _BLOCK_TAGS:
            self._paragraph_break()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._ignored_depth:
            return
        if tag.lower() == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._ignored_depth:
            self._ignored_depth -= 1
            return
        if tag.lower() in _BLOCK_TAGS:
            self._paragraph_break()

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)

    def get_text(self) -> str:
        return "".join(self.parts)


def _strip_html(text: str) -> str:
    parser = _PlainTextHTMLParser()
    parser.feed(text)
    parser.close()
    return parser.get_text()


def _strip_markdown(text: str) -> str:
    # Code blocks are implementation detail rather than prose and should not be read.
    text = re.sub(r"(?ms)^\s*(```|~~~).*?^\s*\1\s*$", "\n\n", text)

    # Preserve human-readable labels while dropping Markdown destinations.
    text = re.sub(
        r"\[!\[([^\]]*)\]\((?:[^()]|\([^()]*\))*\)\]\((?:[^()]|\([^()]*\))*\)",
        r"\1",
        text,
    )
    text = re.sub(r"!\[([^\]]*)\]\((?:[^()]|\([^()]*\))*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\((?:[^()]|\([^()]*\))*\)", r"\1", text)
    text = re.sub(r"`([^`\n]+)`", r"\1", text)

    output_lines: list[str] = []
    for line in text.split("\n"):
        if re.fullmatch(r"\s{0,3}(?:[-*_]\s*){3,}", line):
            output_lines.append("")
            continue
        if re.fullmatch(r"\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*", line):
            continue

        heading = re.match(r"^\s{0,3}#{1,6}[ \t]+(.*)$", line)
        list_item = re.match(r"^\s{0,3}(?:[-+*]|\d{1,9}[.)、])[ \t]+(.*)$", line)
        standalone_bold = re.match(r"^\s*(?:\*\*|__)(.+?)(?:\*\*|__)\s*$", line)

        if heading or list_item or standalone_bold:
            content = (heading or list_item or standalone_bold).group(1)
            output_lines.extend(("", content, ""))
            continue

        line = re.sub(r"^\s{0,3}>[ \t]?", "", line)
        if line.strip().startswith("|") and line.strip().endswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            line = "，".join(cell for cell in cells if cell)
        output_lines.append(line)

    text = "\n".join(output_lines)
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"\\([\\`*{}\[\]()#+.!_>~-])", r"\1", text)
    return text


def _remove_urls(text: str) -> str:
    url_pattern = re.compile(
        r"(?i)\b(?:https?://|ftp://|www\.)"
        r"[^\s<>{}\[\]，。！？；：、（）【】《》「」『』]+"
    )

    def replace_url(match: re.Match[str]) -> str:
        url = match.group(0)
        trailing = url[len(url.rstrip(_TRAILING_URL_PUNCTUATION)) :]
        return trailing

    return url_pattern.sub(replace_url, text)


def _remove_empty_brackets(text: str) -> str:
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"\(\s*\)|（\s*）|\[\s*\]|【\s*】|《\s*》|「\s*」|『\s*』", "", text)
    return text


def _normalize_line_spacing(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    text = re.sub(r"[\u200b-\u200d\ufeff]", "", text)
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text


def _join_soft_wrapped_lines(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    if re.search(r"[\u3400-\u9fff]$", left) and re.match(r"^[\u3400-\u9fff]", right):
        separator = ""
    elif left.endswith(("(", "（", "[", "【", "《", "「", "『", "/", "-")):
        separator = ""
    elif right.startswith(("，", "。", "！", "？", "；", "：", ",", ".", "!", "?", ";", ":", "%", "）", ")")):
        separator = ""
    else:
        separator = " "
    return left.rstrip() + separator + right.lstrip()


def _clean_paragraph_spacing(paragraph: str) -> str:
    paragraph = re.sub(r" +", " ", paragraph).strip()
    paragraph = re.sub(r"\s+([，。、？！；：,.!?;:%）)】》」』])", r"\1", paragraph)
    paragraph = re.sub(r"([（(【《「『])\s+", r"\1", paragraph)
    return paragraph


def _reflow_paragraphs(text: str, merge_soft_line_breaks: bool) -> str:
    paragraphs: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        cleaned = _clean_paragraph_spacing(current)
        if cleaned:
            paragraphs.append(cleaned)
        current = ""

    for line in text.split("\n"):
        line = _clean_paragraph_spacing(line)
        if not line:
            flush()
            continue
        if not merge_soft_line_breaks:
            flush()
            current = line
            flush()
            continue
        if current and current.endswith(_TERMINAL_PUNCTUATION):
            flush()
        current = _join_soft_wrapped_lines(current, line)
    flush()
    return "\n\n".join(paragraphs)


def pre_process_text(text: str, options: dict | None = None) -> str:
    """Convert user input to plain, paragraph-aware text suitable for TTS.

    ``no_line_breaks`` is retained as a backwards-compatible configuration key.
    It now means "merge soft line wraps"; explicit paragraph boundaries and
    sentence-ending lines remain separate so long-form speech keeps its structure.
    """

    if not isinstance(text, str):
        raise TypeError("text must be a string")
    options = options or {}
    processed_text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))

    if options.get("remove_markdown"):
        processed_text = _strip_markdown(processed_text)

    # HTML tags and character entities can arrive independently of Markdown.
    processed_text = _strip_html(processed_text)

    if options.get("remove_emoji"):
        processed_text = emoji.replace_emoji(processed_text, replace="")
    if options.get("no_urls"):
        processed_text = _remove_urls(processed_text)

    custom_keywords = options.get("custom_keywords", "")
    if custom_keywords:
        keywords = [re.escape(keyword.strip()) for keyword in custom_keywords.split(",") if keyword.strip()]
        if keywords:
            processed_text = re.sub("|".join(keywords), "", processed_text)

    processed_text = _remove_empty_brackets(processed_text)
    processed_text = _normalize_line_spacing(processed_text)
    return _reflow_paragraphs(
        processed_text,
        merge_soft_line_breaks=bool(options.get("no_line_breaks")),
    )


def _preferred_split_position(text: str, max_chunk_len: int) -> int:
    """Find the most natural boundary within the current size budget."""

    window = text[: max_chunk_len + 1]
    minimum_useful_position = max(1, int(max_chunk_len * 0.45))
    boundary_patterns = (
        r"[，,；;：:]\s*",
        r"\s+",
        r"[-—–/]",
    )
    for pattern in boundary_patterns:
        positions = [match.end() for match in re.finditer(pattern, window)]
        useful_positions = [
            position
            for position in positions
            if minimum_useful_position <= position <= max_chunk_len
        ]
        if useful_positions:
            return useful_positions[-1]

    # A punctuation-free Chinese sentence may force a hard cut. Move that cut
    # before a numeric expression so values such as 80.7% and 3.0-3.9 survive.
    for match in re.finditer(r"[+-]?\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?%?", text):
        if match.start() < max_chunk_len < match.end() and match.start() > 0:
            return match.start()
    return max_chunk_len


def _split_oversized_segment(segment: str, max_chunk_len: int) -> list[str]:
    if len(segment) <= max_chunk_len:
        return [segment]

    chunks: list[str] = []
    remaining = segment.strip()
    while len(remaining) > max_chunk_len:
        split_at = _preferred_split_position(remaining, max_chunk_len)
        chunk = remaining[:split_at].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _join_chunk_parts(left: str, right: str) -> str:
    """Join sentences without collapsing English words or adding Chinese gaps."""

    if not left:
        return right
    if not right:
        return left
    if re.search(r"[A-Za-z0-9%.,!?;:)\]'”]$", left) and re.match(r"^[A-Za-z0-9([]", right):
        return f"{left} {right}"
    return left + right


def split_text_into_chunks(text: str, max_chunk_len: int = 300) -> list[str]:
    """Create semantic chunks while retaining paragraph boundaries in each chunk."""

    if not isinstance(text, str):
        raise TypeError("text must be a string")
    try:
        max_chunk_len = int(max_chunk_len)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_chunk_len must be an integer") from exc
    if max_chunk_len < 1:
        raise ValueError("max_chunk_len must be greater than zero")

    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    chunks: list[str] = []
    for paragraph in paragraphs:
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[。！？!?])\s*|(?<=\.)\s+(?=[^\s])", paragraph)
            if sentence.strip()
        ]
        current = ""
        paragraph_chunks: list[str] = []
        for sentence in sentences:
            for piece in _split_oversized_segment(sentence, max_chunk_len):
                combined = _join_chunk_parts(current, piece)
                if current and len(combined) > max_chunk_len:
                    paragraph_chunks.append(current)
                    current = piece
                else:
                    current = combined
        if current:
            paragraph_chunks.append(current)

        # Paragraphs are semantic pause boundaries, not mandatory request
        # boundaries. Coalesce short neighbours to avoid many tiny TTS calls.
        if chunks and paragraph_chunks:
            combined = f"{chunks[-1]}\n\n{paragraph_chunks[0]}"
            if len(combined) <= max_chunk_len:
                chunks[-1] = combined
                paragraph_chunks = paragraph_chunks[1:]
        chunks.extend(paragraph_chunks)
    return chunks
