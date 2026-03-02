# ✨ Course Accessibility Checker

A **WCAG 2.2-compliant** accessibility checker for e-learning courses (especially Articulate Rise), powered by **Google Gemini AI** for deep analysis.

Upload a PDF export of your course → get instant automated checks → optionally run AI-powered deep review → generate a final accessibility report with a supportive grade.

---

## Features

| Feature | Description |
|---------|-------------|
| **Automatic WCAG Checks** | PDF title, language, tags, text extractability, readability, ALL CAPS detection, link quality, device-neutral language |
| **Gemini AI Analysis** | Deep content review covering structure, plain language, RISE-specific patterns, and WCAG 2.2 compliance notes |
| **RISE Course Checks** | Interactive block labels, knowledge check accessibility, multimedia alternatives, navigation logic |
| **Manual Checklist** | Confirm items that can't be auto-detected (contrast, font size, alt text quality, keyboard access) |
| **Supportive Scoring** | Grade A–E that doesn't penalise for unconfirmed manual items or PDF export limitations |
| **Shareable Reports** | Public link via Gradio's `share=True` — send the URL to colleagues |

---

## Quick Start

### 1. Install Dependencies

```bash
pip install gradio PyPDF2 google-generativeai
```

### 2. Run the App

```bash
python "Access Checker.py"
```

The terminal will show:
- **Local URL:** `http://127.0.0.1:7880`
- **Public URL:** a `*.gradio.live` link you can share

### 3. Use the App

1. **📄 Upload & Settings** — Drop your course PDF. Optionally paste your [Gemini API key](https://ai.google.dev).
2. **📋 Auto Results** — Click "Run Automatic Checks" to see rule-based WCAG results.
3. **✅ Manual Checklist** — Tick any items you've personally verified in the live course.
4. **🤖 AI Analysis** — Click "Run AI Analysis" for a comprehensive Gemini-powered review.
5. **📜 Final Report** — Click "Generate Final Report" for your combined score and grade.

---

## Gemini AI (Optional)

The AI analysis is **optional** — all rule-based checks work without it.

To enable AI analysis:
1. Get a free API key at [ai.google.dev](https://ai.google.dev)
2. Paste it in the **AI Settings** section on the Upload tab
3. Run automatic checks first, then click **Run AI Analysis**

The AI reviews:
- Content clarity and plain language
- Heading hierarchy and structure
- Image/media accessibility clues
- RISE-specific interactive elements
- WCAG 2.2 success criteria at risk
- Top 5 prioritised recommendations

---

## Scoring

| Grade | Score | Meaning |
|-------|-------|---------|
| **A** | 85–100 | Excellent foundation |
| **B** | 75–84 | Good progress |
| **C** | 65–74 | On the right track |
| **D** | 50–64 | Getting started |
| **E** | 0–49 | Needs more work |

- **Pass** = full points · **Partial** = 85% · **Fail** = 20% (generous, since PDF exports can hide info)
- Unconfirmed manual items are **excluded**, not counted as failures

---

## WCAG 2.2 Criteria Covered

- 1.1.1 Non-text Content (images/alt text)
- 1.2.1–1.2.5 Audio/Video (captions, transcripts)
- 1.4.3 Contrast (manual)
- 2.1.1 Keyboard Access (manual)
- 2.4.2 Page Titled
- 2.4.3 Focus Order (manual)
- 2.4.6 Headings and Labels
- 3.1.1 Language of Page
- 3.1.4 Abbreviations/Acronyms
- 3.2.3 Consistent Navigation (manual)

---

## Requirements

- **Python 3.10+**
- **gradio** (v4+ or v6)
- **PyPDF2**
- **google-generativeai** (optional, for AI features)

---

## File Structure

```
Access Checker.py    # Main application (single file, ~1070 lines)
README.md            # This file
```

---

*Built for accessibility teams reviewing Articulate Rise courses against WCAG 2.2 guidelines.*
