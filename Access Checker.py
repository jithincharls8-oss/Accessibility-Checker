"""
Accessibility Checker with Gemini AI Integration
A premium Gradio-based tool for checking PDF accessibility against WCAG 2.2 guidelines.
Optionally uses Google Gemini AI for deeper, smarter analysis of RISE courses.
"""

import io
import json
import re
import traceback
from typing import List, Dict, Any, Optional, Tuple

import gradio as gr
from PyPDF2 import PdfReader


# =============================================================================
# 1) WCAG 2.2 Checklist (PDF export aware + RISE course items)
# =============================================================================

CHECKLIST = {
    "source": "WCAG 2.2-based Accessibility Checklist (PDF Export Aware + RISE)",
    "items": [
        # --- Auto-checkable from PDF ---
        {"id": "doc_title_present", "category": "Document",
         "description": "The PDF has a clear title in its file properties (WCAG 2.4.2 Page titled).", "weight": 1.0},
        {"id": "doc_language_present", "category": "Document",
         "description": "The PDF says what language it is written in (WCAG 3.1.1 Language of page).", "weight": 1.0},
        {"id": "doc_tagged_pdf", "category": "Document",
         "description": "The PDF includes accessibility 'tags' (structure info for screen readers).", "weight": 2.0},
        {"id": "doc_text_extractable", "category": "Document",
         "description": "Most pages contain real text (not just pictures of text).", "weight": 2.0},

        {"id": "text_plain_language", "category": "Text",
         "description": "The writing looks reasonably easy to read for the intended audience.", "weight": 1.0},
        {"id": "text_avoid_all_caps", "category": "Text",
         "description": "Avoids long ALL CAPS paragraphs (harder to read).", "weight": 1.0},
        {"id": "text_glossary_for_acronyms", "category": "Text",
         "description": "Acronyms/technical words are explained (or there is a glossary).", "weight": 0.8},
        {"id": "text_inclusive_language", "category": "Text",
         "description": "Instructions aren't device-specific (e.g., not only 'click').", "weight": 0.8},

        {"id": "links_descriptive", "category": "Links",
         "description": "Links are clearly described (avoid 'click here').", "weight": 1.5},

        # --- Manual checks ---
        {"id": "text_minimum_font_size", "category": "Visual design",
         "description": "Text size is comfortable to read and works when zoomed in.", "weight": 1.5},
        {"id": "text_colour_contrast", "category": "Visual design",
         "description": "Text has good contrast against the background.", "weight": 2.0},
        {"id": "text_semantic_structure", "category": "Structure",
         "description": "Headings and lists follow a clear, logical structure.", "weight": 1.5},

        {"id": "images_alt_text", "category": "Images",
         "description": "Important images have a text description (alt text / caption / nearby explanation).", "weight": 2.0},
        {"id": "images_avoid_text_in_images", "category": "Images",
         "description": "Avoids using images that contain lots of important text.", "weight": 1.5},

        {"id": "media_captions", "category": "Audio / video",
         "description": "Videos have captions (subtitles).", "weight": 2.0},
        {"id": "media_transcripts", "category": "Audio / video",
         "description": "Audio/video has a transcript when needed.", "weight": 2.0},

        {"id": "keyboard_access", "category": "Interaction",
         "description": "Everything can be done using only a keyboard (no mouse required).", "weight": 2.0},
        {"id": "focus_order", "category": "Interaction",
         "description": "When you press Tab, focus moves in a sensible order.", "weight": 1.5},
        {"id": "consistent_navigation", "category": "Interaction",
         "description": "Navigation is consistent (menus/buttons stay in the same place).", "weight": 1.5},

        # --- RISE-specific checks ---
        {"id": "rise_interactive_labels", "category": "RISE Course",
         "description": "Interactive blocks (accordions, tabs, flashcards) have meaningful labels.", "weight": 1.5},
        {"id": "rise_knowledge_checks", "category": "RISE Course",
         "description": "Knowledge checks / quizzes follow accessible patterns with clear feedback.", "weight": 1.5},
        {"id": "rise_multimedia_alt", "category": "RISE Course",
         "description": "Embedded multimedia (videos, audio, iframes) has proper text alternatives.", "weight": 1.5},
        {"id": "rise_navigation_logical", "category": "RISE Course",
         "description": "Course navigation is logical, sequential, and clearly labelled.", "weight": 1.0},
    ],
}


# =============================================================================
# 2) Scoring policy
# =============================================================================

SCORE_MAP_SUPPORTIVE = {"pass": 1.0, "partial": 0.85, "fail": 0.20}

GRADE_BANDS = [
    (85, "A", "Excellent foundation"),
    (75, "B", "Good progress"),
    (65, "C", "On the right track"),
    (50, "D", "Getting started"),
    (0,  "E", "Needs more work"),
]


# =============================================================================
# 3) PDF Helpers
# =============================================================================

def file_to_bytes(uploaded) -> Optional[bytes]:
    if uploaded is None:
        return None
    if isinstance(uploaded, (bytes, bytearray)):
        return bytes(uploaded)
    if isinstance(uploaded, str):
        with open(uploaded, "rb") as f:
            return f.read()
    if isinstance(uploaded, dict) and "data" in uploaded:
        return uploaded["data"]
    if hasattr(uploaded, "read"):
        return uploaded.read()
    raise TypeError(f"Unsupported upload type: {type(uploaded)}")


def safe_get_pdf_root(reader: PdfReader):
    try:
        return reader.trailer.get("/Root")
    except Exception:
        return None


def extract_text_per_page(reader: PdfReader) -> List[str]:
    out: List[str] = []
    for p in reader.pages:
        try:
            out.append(p.extract_text() or "")
        except Exception:
            out.append("")
    return out


def estimate_image_count(reader: PdfReader) -> int:
    count = 0
    for page in reader.pages:
        try:
            res = page.get("/Resources") or {}
            xobj = res.get("/XObject") if isinstance(res, dict) else None
            if not xobj:
                continue
            xobj = xobj.get_object()
            for _, obj in xobj.items():
                try:
                    obj = obj.get_object()
                    if obj.get("/Subtype") == "/Image":
                        count += 1
                except Exception:
                    continue
        except Exception:
            continue
    return count


# =============================================================================
# 4) Readability scoring
# =============================================================================

def count_syllables(word: str) -> int:
    w = re.sub(r"[^a-zA-Z]", "", word)
    if not w:
        return 0
    w = w.lower()
    vowels = "aeiouy"
    syllables = 0
    prev_vowel = False
    for c in w:
        if c in vowels:
            if not prev_vowel:
                syllables += 1
            prev_vowel = True
        else:
            prev_vowel = False
    if w.endswith("e") and syllables > 1:
        syllables -= 1
    return max(syllables, 1)


def flesch_reading_ease(text: str) -> float:
    words = re.findall(r"\b\w+\b", text)
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    if not words:
        return 0.0
    num_words = len(words)
    num_sentences = max(len(sentences), 1)
    syllables = sum(count_syllables(w) for w in words)
    asl = num_words / num_sentences
    asw = syllables / num_words
    return 206.835 - 1.015 * asl - 84.6 * asw


def flesch_kincaid_grade(text: str) -> float:
    words = re.findall(r"\b\w+\b", text)
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    if not words:
        return 0.0
    num_words = len(words)
    num_sentences = max(len(sentences), 1)
    syllables = sum(count_syllables(w) for w in words)
    asl = num_words / num_sentences
    asw = syllables / num_words
    return 0.39 * asl + 11.8 * asw - 15.59


def readability_band(flesch: float) -> str:
    if flesch >= 90: return "Very easy"
    if flesch >= 80: return "Easy"
    if flesch >= 70: return "Fairly easy"
    if flesch >= 60: return "Plain English"
    if flesch >= 50: return "Fairly difficult"
    if flesch >= 30: return "Difficult"
    return "Very difficult"


# =============================================================================
# 5) Feature extraction
# =============================================================================

def extract_features(course_bytes: bytes, readability_char_cap: int = 50_000) -> Dict[str, Any]:
    reader = PdfReader(io.BytesIO(course_bytes))
    root = safe_get_pdf_root(reader)

    meta_title = ""
    try:
        meta = getattr(reader, "metadata", None)
        if meta and getattr(meta, "title", None):
            meta_title = str(meta.title or "").strip()
    except Exception:
        meta_title = ""

    doc_lang = ""
    try:
        if root and root.get("/Lang"):
            doc_lang = str(root.get("/Lang")).strip()
    except Exception:
        doc_lang = ""

    is_tagged = False
    try:
        if root and root.get("/StructTreeRoot") is not None:
            is_tagged = True
    except Exception:
        is_tagged = False

    page_texts = extract_text_per_page(reader)
    num_pages = len(page_texts)
    pages_with_text = sum(1 for t in page_texts if len((t or "").strip()) >= 20)
    text_page_ratio = pages_with_text / max(num_pages, 1)

    full_text = "\n".join(page_texts)
    text_for_readability = full_text[:readability_char_cap]

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", full_text) if p.strip()]

    def mostly_all_caps(par: str) -> bool:
        letters = [c for c in par if c.isalpha()]
        if not letters:
            return False
        upper = sum(1 for c in letters if c.isupper())
        return (upper / len(letters)) > 0.8

    caps_pars = [p for p in paragraphs if len(p) > 20 and mostly_all_caps(p)]
    all_caps_ratio = len(caps_pars) / max(len(paragraphs), 1)

    acronyms = sorted(set(re.findall(r"\b[A-Z]{3,}\b", full_text)))

    lower = full_text.lower()
    click_count = len(re.findall(r"\bclick\b", lower))
    agnostic_verbs = ["select", "tap", "choose", "press", "activate"]
    agnostic_count = sum(len(re.findall(rf"\b{re.escape(v)}\b", lower)) for v in agnostic_verbs)

    links_total = len(re.findall(r"https?://\S+|www\.\S+", full_text))
    click_here_count = len(re.findall(r"\bclick here\b", lower))

    flesch = flesch_reading_ease(text_for_readability)
    fk_grade = flesch_kincaid_grade(text_for_readability)

    image_count = estimate_image_count(reader)

    return {
        "meta_title": meta_title, "doc_lang": doc_lang, "is_tagged": is_tagged,
        "num_pages": num_pages, "pages_with_text": pages_with_text,
        "text_page_ratio": text_page_ratio, "all_caps_ratio": all_caps_ratio,
        "acronyms": acronyms, "click_count": click_count,
        "agnostic_count": agnostic_count, "agnostic_verbs": agnostic_verbs,
        "links_total": links_total, "click_here_count": click_here_count,
        "flesch": flesch, "fk_grade": fk_grade, "image_count": image_count,
        "readability_char_cap": readability_char_cap, "full_text": full_text,
    }


# =============================================================================
# 6) Evaluation + supportive scoring
# =============================================================================

def pretty_label(item: Dict[str, Any]) -> str:
    return f"{item['category']}: {item['description']}"


def grade_from_score(score: float) -> Tuple[str, str]:
    for cutoff, letter, label in GRADE_BANDS:
        if score >= cutoff:
            return letter, label
    return "E", "Needs more work"


def compute_score_supportive(items, include_statuses=None):
    if include_statuses is None:
        include_statuses = set(SCORE_MAP_SUPPORTIVE.keys())
    total_w = 0.0
    total_pts = 0.0
    for it in items:
        s = it["status"]
        if s in include_statuses:
            w = float(it["weight"])
            total_w += w
            total_pts += w * SCORE_MAP_SUPPORTIVE.get(s, 0.0)
    score = round((100.0 * total_pts / total_w), 1) if total_w > 0 else 0.0
    letter, label = grade_from_score(score)
    return {"score": score, "grade": letter, "grade_label": label, "denominator_weight": round(total_w, 2)}


def static_evaluate(checklist, feat):
    out = []
    for item in checklist["items"]:
        cid = item["id"]
        w = float(item["weight"])
        status = "manual"
        reason = ""

        if cid == "doc_title_present":
            t = (feat["meta_title"] or "").strip()
            if t and t.lower() not in {"untitled", "unknown"}:
                status, reason = "pass", f'Good: the PDF title is set to \u201c{t}\u201d.'
            else:
                status, reason = "fail", "The PDF title is missing. This is usually an easy fix in the export settings."

        elif cid == "doc_language_present":
            lang = (feat["doc_lang"] or "").strip()
            if lang:
                status, reason = "pass", f'Good: the PDF language is set to \u201c{lang}\u201d.'
            else:
                status, reason = "fail", "The PDF does not say what language it is. Screen readers may mispronounce words without this."

        elif cid == "doc_tagged_pdf":
            if feat["is_tagged"]:
                status, reason = "pass", "Good: the PDF looks like it includes accessibility tags."
            else:
                status, reason = "fail", "No accessibility tags detected. Tags help screen readers. Re-export as a tagged PDF if possible."

        elif cid == "doc_text_extractable":
            ratio = feat["text_page_ratio"]
            if ratio >= 0.8:
                status, reason = "pass", f"Good: most pages contain real text ({ratio*100:.1f}%)."
            elif ratio >= 0.5:
                status, reason = "partial", f"Mixed: only some pages contain real text ({ratio*100:.1f}%)."
            else:
                status, reason = "fail", f"Most pages look like images of text ({ratio*100:.1f}% with real text)."

        elif cid == "text_plain_language":
            f = feat["flesch"]
            g = feat["fk_grade"]
            band = readability_band(f)
            status = "pass" if f >= 55 else ("partial" if f >= 35 else "fail")
            reason = f"Reading score: Ease \u2248 {f:.1f} ({band}); Grade level \u2248 {g:.1f}. This is a helpful clue, not a strict rule."

        elif cid == "text_avoid_all_caps":
            r = feat["all_caps_ratio"]
            if r == 0:
                status, reason = "pass", "Good: no long ALL CAPS paragraphs detected."
            elif r < 0.20:
                status, reason = "partial", f"Some ALL CAPS text detected (~{r*100:.1f}%). Consider switching to sentence case."
            else:
                status, reason = "fail", f"A lot of ALL CAPS text detected (~{r*100:.1f}%)."

        elif cid == "text_glossary_for_acronyms":
            acr = feat["acronyms"]
            if not acr:
                status, reason = "not_applicable", "No acronyms detected."
            else:
                status = "manual"
                reason = f"Acronyms detected (examples: {', '.join(acr[:8])}). Please confirm they are explained."

        elif cid == "text_inclusive_language":
            click_ct = feat["click_count"]
            ag_ct = feat["agnostic_count"]
            if click_ct == 0 and ag_ct > 0:
                status, reason = "pass", 'Good: instructions use device-neutral words and do not rely on \u201cclick\u201d.'
            elif click_ct == 0 and ag_ct == 0:
                status, reason = "manual", "No clear instruction words detected. Quick manual check recommended."
            else:
                status, reason = "partial", f'Found \u201cclick\u201d {click_ct} time(s). Device-neutral words found {ag_ct} time(s). Prefer select/choose/tap.'

        elif cid == "links_descriptive":
            total = feat["links_total"]
            ch = feat["click_here_count"]
            if total == 0 and ch == 0:
                status, reason = "not_applicable", "No links detected in the extracted text."
            elif ch == 0:
                status, reason = "pass", 'Good: \u201cclick here\u201d was not detected.'
            else:
                status = "partial" if (total > 0 and ch < total) else "fail"
                reason = '\u201cClick here\u201d was detected. Links are clearer when they describe what they do.'

        elif cid.startswith("rise_"):
            status = "manual"
            reason = "RISE-specific check \u2014 requires manual review of the live course or source."

        else:
            status = "manual"
            reason = "This needs a human check (a PDF export cannot reliably measure this)."

        out.append({"id": cid, "category": item["category"], "description": item["description"],
                     "status": status, "weight": w, "reason": reason})
    return {"items": out}


def top_next_steps(items, k=3):
    def key(it):
        status_rank = {"fail": 0, "partial": 1, "pass": 2, "manual": 3, "not_applicable": 4, "unconfirmed": 5}
        return (status_rank.get(it["status"], 9), -float(it["weight"]))
    actionable = [it for it in items if it["status"] in {"fail", "partial"}]
    actionable.sort(key=key)
    return actionable[:k]


def confidence_label(manual_done, manual_total):
    if manual_total <= 0:
        return "High (no manual checks needed)"
    ratio = manual_done / manual_total
    if ratio >= 0.67:
        return "High (you confirmed most items)"
    if ratio >= 0.34:
        return "Medium (some items confirmed)"
    return "Low (few items confirmed yet)"


# =============================================================================
# 7) Gemini AI deep analysis
# =============================================================================

def _try_gemini_call(genai, api_key: str, prompt: str) -> str:
    """Try calling Gemini with fallback models. Returns response text or raises."""
    genai.configure(api_key=api_key.strip())

    # Try models in order of preference
    models_to_try = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
    last_error = None

    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            if response and response.text:
                return response.text
        except Exception as e:
            last_error = e
            continue

    if last_error:
        raise last_error
    raise RuntimeError("All Gemini models failed to produce a response.")


def run_gemini_analysis(api_key: str, full_text: str, feat: Dict[str, Any], eval_items: list) -> str:
    """Send document text to Gemini for deep accessibility analysis."""
    if not api_key or not api_key.strip():
        return ""

    # Validate API key format
    key = api_key.strip()
    if len(key) < 10:
        return "**\u274c Invalid API key.** The key looks too short. Please paste your full Gemini API key."

    try:
        import google.generativeai as genai
    except ImportError:
        return (
            "**\u26a0\ufe0f The `google-generativeai` package is not installed.**\n\n"
            "Run this command in your terminal or Anaconda Prompt:\n\n"
            "```\npip install google-generativeai\n```\n\n"
            "Then restart the app."
        )

    try:
        # Build context about what the rule-based checker already found
        auto_findings = []
        for it in eval_items:
            icon = {"pass": "\u2705", "partial": "\u26a0\ufe0f", "fail": "\u274c"}.get(it["status"], "\u2753")
            auto_findings.append(f"{icon} [{it['status'].upper()}] {it['category']}: {it['description']} \u2014 {it['reason']}")

        auto_summary = "\n".join(auto_findings)

        # Cap the text sent to AI to avoid token limits
        text_sample = full_text[:80_000] if full_text else "(No text was extracted from this PDF.)"

        prompt = f"""You are a senior accessibility expert reviewing an e-learning course document (likely created in Articulate Rise or similar).
The document has already been checked by an automated tool. Here are the automated findings:

{auto_summary}

Below is the full extracted text from the PDF (up to 80,000 characters):

---START DOCUMENT TEXT---
{text_sample}
---END DOCUMENT TEXT---

Document metadata:
- Pages: {feat.get('num_pages', 'unknown')}
- Images detected: {feat.get('image_count', 'unknown')}
- Flesch Reading Ease: {feat.get('flesch', 0):.1f}
- Flesch-Kincaid Grade: {feat.get('fk_grade', 0):.1f}

Please provide a comprehensive accessibility review covering:

## 1. Executive Summary
A 2-3 sentence overview of the document's accessibility status.

## 2. Content & Language Analysis
- Is the language clear and plain enough for the intended audience?
- Are there jargon or acronyms that need explanation?
- Are instructions device-neutral (not just "click")?

## 3. Structure & Navigation
- Does the document follow a logical heading hierarchy?
- Are there skipped heading levels?
- Is the reading order clear?

## 4. Images & Media
- Based on context clues, do images appear to have adequate descriptions?
- Are there references to visual content that may lack alternatives?

## 5. RISE Course-Specific Issues
- Are there interactive elements (accordions, tabs, flashcards) that may need labels?
- Are knowledge checks accessible?
- Is multimedia content properly referenced?

## 6. WCAG 2.2 Compliance Notes
- List specific WCAG 2.2 success criteria that may be at risk
- Reference the relevant criterion number (e.g., 1.1.1, 2.4.2)

## 7. Top 5 Priority Recommendations
Numbered list of the most impactful changes to improve accessibility, with specific guidance on how to fix each one.

Format your response in clean Markdown. Be specific and actionable. Reference exact text from the document when possible."""

        return _try_gemini_call(genai, key, prompt)

    except Exception as e:
        error_msg = str(e)
        if "API_KEY_INVALID" in error_msg or "401" in error_msg:
            return "**\u274c Invalid API Key.** Please double-check your Gemini API key and try again.\n\nGet a free key at [ai.google.dev](https://ai.google.dev)"
        if "quota" in error_msg.lower() or "429" in error_msg:
            return "**\u26a0\ufe0f Rate limit reached.** Please wait a minute and try again, or check your API quota."
        if "permission" in error_msg.lower() or "403" in error_msg:
            return "**\u274c Permission denied.** Make sure the Gemini API is enabled for your Google Cloud project."
        return f"**\u274c Gemini AI Error:** {error_msg}\n\nPlease check your API key is valid and try again."


# =============================================================================
# 8) Gradio callbacks
# =============================================================================

def build_glossary_md() -> str:
    return (
        "### Plain-English glossary\n"
        "- **PDF title / metadata:** Extra info saved inside the PDF. Screen readers use it to identify the document.\n"
        "- **PDF language:** Tells assistive tech what language to use for pronunciation.\n"
        "- **Tagged PDF:** The PDF contains structure info (headings, reading order, lists) for screen readers.\n"
        "- **Extractable text:** Real text you can highlight and copy (vs. scanned images).\n"
        "- **Readability score:** A rough estimate of how complex the writing is. Guidance only.\n"
        "- **Device-neutral instructions:** Words like 'select/choose' work for mouse, keyboard, and touch.\n"
    )


def analyze_course(course_file):
    try:
        course_bytes = file_to_bytes(course_file)
    except Exception as e:
        return f"**Error reading PDF:** {e}", gr.update(choices=[], value=[]), "", ""

    if not course_bytes:
        return "**Please upload a PDF to begin.**", gr.update(choices=[], value=[]), "", ""

    try:
        feat = extract_features(course_bytes)
    except Exception as e:
        return f"**Could not analyse the PDF:** {e}", gr.update(choices=[], value=[]), "", ""

    evaluation = static_evaluate(CHECKLIST, feat)
    items = evaluation["items"]
    auto = compute_score_supportive(items)

    passed = [it for it in items if it["status"] == "pass"]
    partial = [it for it in items if it["status"] == "partial"]
    failed = [it for it in items if it["status"] == "fail"]
    manual = [it for it in items if it["status"] == "manual"]
    na = [it for it in items if it["status"] == "not_applicable"]

    manual_labels = [pretty_label(it) for it in manual]
    label_to_id = {pretty_label(it): it["id"] for it in manual}
    next_steps = top_next_steps(items, k=3)

    lines = []
    lines.append("## \U0001f4cb Automatic Check Results")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| **Score** | {auto['score']} / 100 |")
    lines.append(f"| **Grade** | {auto['grade']} \u2014 {auto['grade_label']} |")
    lines.append(f"| **Pages** | {feat['num_pages']} |")
    lines.append(f"| **Pages with text** | {feat['pages_with_text']} ({feat['text_page_ratio']*100:.1f}%) |")
    lines.append(f"| **Images** | {feat['image_count']} |")
    lines.append(f"| **PDF title** | {'Yes \u2014 ' + feat['meta_title'] if (feat['meta_title'] or '').strip() else 'No'} |")
    lines.append(f"| **Language set** | {feat['doc_lang'] if (feat['doc_lang'] or '').strip() else 'No'} |")
    lines.append(f"| **Tagged PDF** | {'Yes' if feat['is_tagged'] else 'No'} |")
    lines.append(f"| **Readability** | {feat['flesch']:.1f} ({readability_band(feat['flesch'])}) \u2014 Grade {feat['fk_grade']:.1f} |")
    lines.append("")
    lines.append(build_glossary_md())
    lines.append("")

    if next_steps:
        lines.append("### \U0001f680 Top Recommended Actions")
        for it in next_steps:
            lines.append(f"- **{pretty_label(it)}**  \n  {it['reason']}")
        lines.append("")

    lines.append("### \u2705 Passed")
    lines.extend(["- None."] if not passed else [f"- **{pretty_label(it)}**  \n  {it['reason']}" for it in passed])
    lines.append("")
    lines.append("### \u26a0\ufe0f Needs Improvement")
    lines.extend(["- None."] if not partial else [f"- **{pretty_label(it)}**  \n  {it['reason']}" for it in partial])
    lines.append("")
    lines.append("### \u274c Needs Attention")
    lines.extend(["- None."] if not failed else [f"- **{pretty_label(it)}**  \n  {it['reason']}" for it in failed])
    lines.append("")

    if na:
        lines.append("### \u2139\ufe0f Not Applicable")
        for it in na:
            lines.append(f"- **{pretty_label(it)}**  \n  {it['reason']}")
        lines.append("")

    summary_md = "\n".join(lines)

    state_obj = {
        "evaluation": evaluation,
        "label_to_id": label_to_id,
        "manual_total": len(manual_labels),
        "feat": {k: v for k, v in feat.items() if k != "full_text"},
        "full_text": feat["full_text"][:100_000],
    }

    progress_md = f"**Manual checklist progress:** 0 / {len(manual_labels)} confirmed"
    return summary_md, gr.update(choices=manual_labels, value=[]), json.dumps(state_obj), progress_md


def run_ai_check(api_key, evaluation_state):
    if not api_key or not api_key.strip():
        return "\u26a0\ufe0f **Please enter your Google Gemini API key** in the Settings tab to use AI-powered analysis."

    if not evaluation_state:
        return "\u26a0\ufe0f **Please run automatic checks first** (Tab 1) before using AI analysis."

    try:
        state = json.loads(evaluation_state)
        feat = state.get("feat", {})
        full_text = state.get("full_text", "")
        eval_items = state["evaluation"]["items"]

        result = run_gemini_analysis(api_key, full_text, feat, eval_items)
        if not result:
            return "\u274c No response from Gemini. Please check your API key."

        return f"# \U0001f916 AI-Powered Accessibility Analysis\n\n{result}"

    except Exception as e:
        return f"\u274c **Error:** {str(e)}"


def update_manual_progress(manual_checked, evaluation_state):
    if not evaluation_state:
        return "**Manual checklist progress:** 0 / 0 confirmed"
    try:
        state = json.loads(evaluation_state)
        total = int(state.get("manual_total", 0))
    except Exception:
        total = 0
    selected = len(manual_checked or [])
    return f"**Manual checklist progress:** {selected} / {total} confirmed"


def finalize_grade(manual_checked, evaluation_state):
    if not evaluation_state:
        return "Please run **Analyze course** first."

    state = json.loads(evaluation_state)
    evaluation = state["evaluation"]
    label_to_id = state["label_to_id"]
    manual_total = int(state.get("manual_total", 0))

    selected_ids = {label_to_id[label] for label in (manual_checked or []) if label in label_to_id}
    manual_done = len(selected_ids)

    updated_items = []
    for it in evaluation["items"]:
        if it["status"] == "manual":
            updated = dict(it)
            if it["id"] in selected_ids:
                updated["status"] = "pass"
                updated["reason"] = "Confirmed in the manual checklist."
            else:
                updated["status"] = "unconfirmed"
                updated["reason"] = "Not confirmed yet (excluded from scoring)."
            updated_items.append(updated)
        else:
            updated_items.append(it)

    final = compute_score_supportive(updated_items)
    passed = [it for it in updated_items if it["status"] == "pass"]
    partial = [it for it in updated_items if it["status"] == "partial"]
    failed = [it for it in updated_items if it["status"] == "fail"]
    unconfirmed = [it for it in updated_items if it["status"] == "unconfirmed"]
    conf = confidence_label(manual_done, manual_total)
    next_steps = top_next_steps(updated_items, k=5)

    lines = []
    lines.append("## \U0001f3c6 Final Accessibility Report")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| **Final Score** | {final['score']} / 100 |")
    lines.append(f"| **Grade** | {final['grade']} \u2014 {final['grade_label']} |")
    lines.append(f"| **Confidence** | {conf} |")
    lines.append(f"| **Manual items confirmed** | {manual_done} / {manual_total} |")
    lines.append("")
    lines.append("### What this means")
    lines.append(
        "- The score includes automatic checks **plus** any manual items you confirmed.\n"
        "- Unticked manual items are **not confirmed yet** (they do NOT reduce your score)."
    )
    lines.append("")
    if next_steps:
        lines.append("### \U0001f680 Recommended Next Steps")
        for it in next_steps:
            lines.append(f"- **{pretty_label(it)}**  \n  {it['reason']}")
        lines.append("")
    lines.append("### \u2705 Met Criteria")
    lines.extend(["- None."] if not passed else [f"- **{pretty_label(it)}**" for it in passed])
    lines.append("")
    lines.append("### \u26a0\ufe0f Partially Met")
    lines.extend(["- None."] if not partial else [f"- **{pretty_label(it)}**" for it in partial])
    lines.append("")
    lines.append("### \u274c Needs Attention")
    lines.extend(["- None."] if not failed else [f"- **{pretty_label(it)}**" for it in failed])
    lines.append("")
    lines.append(f"### \U0001f552 Not Confirmed Yet")
    lines.append(f"- **{len(unconfirmed)}** item(s) not confirmed. Confirming more increases confidence.")

    return "\n".join(lines)


# =============================================================================
# 9) Premium UI
# =============================================================================

custom_css = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

:root {
  --bg-primary: #f8f7fc;
  --bg-secondary: #ffffff;
  --bg-card: #ffffff;
  --accent-1: #6d28d9;
  --accent-2: #7c3aed;
  --accent-3: #5b21b6;
  --text-primary: #1e1b2e;
  --text-secondary: #57527a;
  --border-subtle: rgba(109, 40, 217, 0.18);
  --border-glow: rgba(124, 58, 237, 0.30);
  --success: #059669;
  --warning: #d97706;
  --error: #dc2626;
  --gradient-header: linear-gradient(135deg, #6d28d9 0%, #7c3aed 50%, #a78bfa 100%);
}

* { font-family: 'Inter', system-ui, -apple-system, sans-serif !important; }
body, .gradio-container { background: var(--bg-primary) !important; color: var(--text-primary) !important; }
.gradio-container { max-width: 1200px !important; margin: 0 auto !important; }
.gradio-container, .gradio-container * { color: var(--text-primary) !important; }

/* Header */
.app-header {
  background: linear-gradient(135deg, rgba(109,40,217,0.08), rgba(124,58,237,0.04)) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 20px !important;
  padding: 24px 28px !important;
  margin-bottom: 8px !important;
}
.app-header h1 {
  background: var(--gradient-header) !important;
  -webkit-background-clip: text !important;
  -webkit-text-fill-color: transparent !important;
  background-clip: text !important;
  font-weight: 800 !important;
  font-size: 28px !important;
  margin: 0 !important;
}
.app-header p { color: var(--text-secondary) !important; }

/* Cards / surfaces */
.surface-card {
  background: var(--bg-card) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 16px !important;
  padding: 16px !important;
  box-shadow: 0 1px 4px rgba(109,40,217,0.06) !important;
}
.surface-card *, .surface-card .prose, .surface-card .markdown,
.surface-card pre, .surface-card code,
.surface-card .wrap, .surface-card .gr-panel, .surface-card .form {
  background: transparent !important;
  box-shadow: none !important;
}

/* Tabs */
.tabs { border: none !important; }
.tab-nav { border: none !important; background: transparent !important; gap: 4px !important; }
.tab-nav button {
  border: 1px solid var(--border-subtle) !important;
  border-radius: 12px !important;
  background: var(--bg-card) !important;
  color: var(--text-secondary) !important;
  padding: 10px 20px !important;
  font-weight: 600 !important;
  font-size: 13px !important;
  transition: all 0.2s ease !important;
}
.tab-nav button.selected {
  background: linear-gradient(135deg, var(--accent-1), var(--accent-2)) !important;
  color: white !important;
  -webkit-text-fill-color: white !important;
  border-color: var(--accent-2) !important;
  box-shadow: 0 4px 15px rgba(109,40,217,0.20) !important;
}
.tabitem { border: none !important; background: transparent !important; }

/* Buttons */
.action-btn button {
  width: 100% !important;
  border-radius: 14px !important;
  padding: 14px 20px !important;
  font-weight: 700 !important;
  font-size: 14px !important;
  border: none !important;
  background: linear-gradient(135deg, var(--accent-1), var(--accent-2)) !important;
  color: white !important;
  -webkit-text-fill-color: white !important;
  box-shadow: 0 4px 15px rgba(109,40,217,0.20) !important;
  transition: all 0.2s ease !important;
  cursor: pointer !important;
}
.action-btn button:hover {
  box-shadow: 0 6px 25px rgba(109,40,217,0.30) !important;
  transform: translateY(-1px) !important;
}

.secondary-btn button {
  width: 100% !important;
  border-radius: 14px !important;
  padding: 14px 20px !important;
  font-weight: 600 !important;
  border: 1px solid var(--border-glow) !important;
  background: var(--bg-card) !important;
  color: var(--accent-3) !important;
}

/* Inputs */
input[type="password"], input[type="text"], textarea {
  background: var(--bg-primary) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 12px !important;
  color: var(--text-primary) !important;
  padding: 12px 16px !important;
}
input[type="password"]:focus, input[type="text"]:focus {
  border-color: var(--accent-2) !important;
  box-shadow: 0 0 0 2px rgba(124,58,237,0.12) !important;
}

/* Checkbox styling */
.checklist-card label {
  display: flex !important;
  align-items: flex-start !important;
  gap: 12px !important;
  padding: 14px !important;
  border-radius: 14px !important;
  border: 1px solid var(--border-subtle) !important;
  margin: 8px 0 !important;
  background: var(--bg-card) !important;
  transition: all 0.2s ease !important;
}
.checklist-card label:has(input:checked) {
  background: rgba(109, 40, 217, 0.08) !important;
  border-color: var(--accent-2) !important;
}
input[type="checkbox"] {
  accent-color: var(--accent-2) !important;
  transform: scale(1.3) !important;
}

/* File upload */
.file-upload .wrap, .file-upload [data-testid="dropzone"] {
  background: var(--bg-card) !important;
  border: 2px dashed var(--border-subtle) !important;
  border-radius: 16px !important;
}

/* Markdown tables */
table { border-collapse: collapse !important; width: 100% !important; margin: 12px 0 !important; }
th { background: rgba(109,40,217,0.06) !important; color: var(--text-primary) !important; padding: 10px 14px !important; text-align: left !important; font-weight: 600 !important; border-bottom: 2px solid var(--border-glow) !important; }
td { padding: 8px 14px !important; border-bottom: 1px solid var(--border-subtle) !important; color: var(--text-primary) !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: var(--bg-primary); }
::-webkit-scrollbar-thumb { background: var(--accent-1); border-radius: 3px; }

/* Labels and text clarity */
label, .label-wrap, span { color: var(--text-primary) !important; }
.gr-checkboxgroup, .gr-checkbox { font-size: 14px !important; line-height: 1.45 !important; }
h1, h2, h3, h4, h5, h6 { color: var(--text-primary) !important; }
p, li, td, th { color: var(--text-primary) !important; }
a { color: var(--accent-1) !important; }
strong { color: var(--text-primary) !important; }
"""

# ---- Build the Gradio app ----

with gr.Blocks(title="Accessibility Checker \u2014 AI-Powered") as demo:

    # -- Header --
    gr.HTML("""
    <div class="app-header">
        <h1>\u2728 Course Accessibility Checker</h1>
        <p style="color: #57527a; margin: 8px 0 0; font-size: 14px;">
            Upload a <strong>PDF</strong> of your course. Get automatic WCAG 2.2 checks, 
            then optionally use <strong>Google Gemini AI</strong> for deeper analysis.
            <br><em>RISE course-aware \u2022 WCAG 2.2 \u2022 Supportive scoring</em>
        </p>
    </div>
    """)

    eval_state = gr.State("")

    with gr.Tabs():

        # ===== TAB 1: Upload & Settings =====
        with gr.Tab("\U0001f4c4 Upload & Settings"):
            with gr.Row():
                with gr.Column(scale=1, min_width=360):
                    gr.Markdown("### Upload Your PDF")
                    course_input = gr.File(
                        label="Drop your course PDF here",
                        file_types=[".pdf"],
                        type="filepath",
                        elem_classes=["file-upload"],
                    )
                    analyze_btn = gr.Button(
                        "\U0001f50d Run Automatic Checks",
                        elem_classes=["action-btn"],
                    )

                with gr.Column(scale=1, min_width=360):
                    gr.Markdown("### \U0001f916 AI Settings (Optional)")
                    gr.Markdown(
                        "Enter your **Google Gemini API key** to unlock AI-powered deep analysis. "
                        "Without a key, the tool still runs all rule-based checks.\n\n"
                        "*Get a free key at [ai.google.dev](https://ai.google.dev)*"
                    )
                    api_key_input = gr.Textbox(
                        label="Gemini API Key",
                        placeholder="AIzaSy...",
                        type="password",
                        elem_classes=["surface-card"],
                    )

        # ===== TAB 2: Automatic Results =====
        with gr.Tab("\U0001f4cb Auto Results"):
            auto_summary = gr.Markdown(
                value="*Run automatic checks from the Upload tab to see results here.*",
                elem_classes=["surface-card"],
            )

        # ===== TAB 3: Manual Checklist =====
        with gr.Tab("\u2705 Manual Checklist"):
            gr.Markdown(
                "### Confirm Manual Checks\n"
                "These items can't be measured reliably from a PDF export. "
                "Tick the ones you've personally verified. "
                "Unticked items are treated as **not confirmed yet** (they won't reduce your score)."
            )
            manual_progress = gr.Markdown(
                "**Manual checklist progress:** 0 / 0 confirmed",
                elem_classes=["surface-card"],
            )
            manual_checklist = gr.CheckboxGroup(
                label="Manual checklist",
                choices=[],
                value=[],
                interactive=True,
                elem_classes=["surface-card", "checklist-card"],
            )
            final_btn = gr.Button(
                "\U0001f3c6 Generate Final Report",
                elem_classes=["action-btn"],
            )

        # ===== TAB 4: AI Analysis =====
        with gr.Tab("\U0001f916 AI Analysis"):
            gr.Markdown(
                "### AI-Powered Deep Analysis\n"
                "Click below to send your document to **Google Gemini** for comprehensive accessibility review. "
                "This covers content quality, structure, RISE-specific issues, and WCAG 2.2 compliance.\n\n"
                "*Requires: (1) a Gemini API key entered in Settings, (2) automatic checks already run.*"
            )
            ai_btn = gr.Button(
                "\U0001f680 Run AI Analysis",
                elem_classes=["action-btn"],
            )
            ai_output = gr.Markdown(
                value="*AI analysis results will appear here.*",
                elem_classes=["surface-card"],
            )

        # ===== TAB 5: Final Report =====
        with gr.Tab("\U0001f4dc Final Report"):
            final_report = gr.Markdown(
                value="*Generate your final report from the Manual Checklist tab.*",
                elem_classes=["surface-card"],
            )

    # ---- Wire up events ----
    analyze_btn.click(
        fn=analyze_course,
        inputs=[course_input],
        outputs=[auto_summary, manual_checklist, eval_state, manual_progress],
    )

    manual_checklist.change(
        fn=update_manual_progress,
        inputs=[manual_checklist, eval_state],
        outputs=[manual_progress],
    )

    ai_btn.click(
        fn=run_ai_check,
        inputs=[api_key_input, eval_state],
        outputs=[ai_output],
    )

    final_btn.click(
        fn=finalize_grade,
        inputs=[manual_checklist, eval_state],
        outputs=[final_report],
    )

# Run:
demo.launch(css=custom_css, server_port=7880, share=True)
