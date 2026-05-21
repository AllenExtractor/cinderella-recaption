"""
caption_builder.py — Builds cc1-style captions for videos and PDFs.
Uses global batch_name and credit_name from settings.
"""
import globals

def build_video_caption(vid_id: int, title: str, ext: str = "mp4") -> str:
    """
    cc1 style video caption.
    📹 VID_ID: 001.
    📝 Title: <title>.<ext>
    📚 Batch Name: <batch_name>
    📥 Extracted By♠ : <credit_name>
    ➽━━━⊱...Team★Toxic...⊰━━━❥
    """
    b_name = globals.get_setting("batch_name", "💥Contact: @CinderellaContactBot")
    cr     = globals.get_setting("credit_name", globals.CR)

    caption = (
        f"**📹 VID_ID: {str(vid_id).zfill(3)}.\n\n"
        f"📝 Title: {title} .{ext}\n\n"
        f"<pre><code>📚 Batch Name: {b_name}</code></pre>\n\n"
        f"📥 Extracted By♠ : {cr}\n\n"
        f"**➽━━━⊱∘₊𝙏𝙚𝙖𝙢★𝙏𝙤𝙭𝙞𝙘₊∘⊰━━━❥**"
    )
    return caption


def build_pdf_caption(pdf_id: int, title: str) -> str:
    """
    cc1 style PDF caption.
    💾 PDF_ID: 001.
    📝 Title: <title>.pdf
    📚 Batch Name: <batch_name>
    📥 Extracted By♠ : <credit_name>
    ➽━━━⊱...Team★Toxic...⊰━━━❥
    """
    b_name = globals.get_setting("batch_name", "💥Contact: @CinderellaContactBot")
    cr     = globals.get_setting("credit_name", globals.CR)

    caption = (
        f"**💾 PDF_ID: {str(pdf_id).zfill(3)}.\n\n"
        f"📝 Title: {title} .pdf\n\n"
        f"<pre><code>📚 Batch Name: {b_name}</code></pre>\n\n"
        f"📥 Extracted By♠ : {cr}\n\n"
        f"**➽━━━⊱∘₊𝙏𝙚𝙖𝙢★𝙏𝙤𝙭𝙞𝙘₊∘⊰━━━❥**"
    )
    return caption


def extract_title_from_caption(caption_text: str) -> str:
    """
    Try to extract Title from a Telegram message caption.
    Looks for 'Title:' or 'Title :' followed by the long title text.
    Falls back to empty string if not found.
    """
    if not caption_text:
        return ""
    import re
    # Pattern: Title: <text> (up to newline or end)
    match = re.search(r'[Tt]itle\s*[:\-]\s*(.+)', caption_text)
    if match:
        raw = match.group(1).strip()
        # Remove extension-like suffixes and trailing spaces
        raw = re.sub(r'\s*\.(mp4|mkv|avi|mov|webm|flv|pdf|m4v|ts)$', '', raw, flags=re.IGNORECASE)
        return raw.strip()
    return ""


def get_title_from_file_or_caption(file_name: str, caption_text: str = "") -> str:
    """
    Priority:
    1. If file_name has a meaningful name (not just 'video' or 'file'), strip extension and use it.
    2. Otherwise extract from caption using 'Title:' pattern.
    3. If still nothing, return file_name without extension.
    """
    import os, re
    generic_names = {"video", "file", "document", "audio", "photo", "unnamed"}

    name_no_ext, _ = os.path.splitext(file_name) if file_name else ("", "")
    name_clean = re.sub(r'[_\-]+', ' ', name_no_ext).strip()

    if name_clean.lower() not in generic_names and len(name_clean) > 3:
        return name_clean

    # Try caption
    from_cap = extract_title_from_caption(caption_text)
    if from_cap:
        return from_cap

    return name_clean or file_name or "Unknown"
