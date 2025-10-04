from typing import Dict

def note_style_summary(doc: Dict) -> Dict:
    """
    Convert a document into a simple note-style summary.
    For now: take abstract text and shorten it into bullets.
    """
    abstract = doc.get("abstract", "")
    bullets = []

    if abstract:
        # Just grab first 2 sentences for now
        sentences = abstract.replace("\n", " ").split(". ")
        for sent in sentences[:2]:
            bullets.append(f"- {sent.strip()}.")

    return {
        "title": doc.get("title", "Untitled"),
        "url": doc.get("url"),
        "bullets": bullets,
        "source": doc.get("source", "unknown")
    }
