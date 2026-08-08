import html


def escape_html(text: str) -> str:
    """
    Escape user-supplied text before interpolating it into a parse_mode="HTML"
    message. Telegram's HTML parser rejects malformed/unexpected tags, and
    unescaped input would also let one user inject markup/links into a
    message rendered on their partner's device.
    """
    return html.escape(text, quote=False)
