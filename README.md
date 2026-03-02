What this code is

It’s a small web app (built with Gradio) that lets you upload a PDF (e.g., a course handout exported from Rise/Word/etc.), then:

Runs automatic accessibility checks it can infer from the PDF itself (metadata, tagging signals, text extractability, basic readability signals, link wording patterns, etc.)

Shows a supportive score + grade and a written report

Lets a human tick off manual checks that a PDF export can’t reliably measure (contrast, keyboard focus order, captions, etc.)

Generates a final report that includes your confirmed manual items without penalising unchecked ones.

What you can do with it (practical use-cases)

Quick QA before publishing PDFs to an LMS/SharePoint/CONNECT

Compare exports (e.g., “tagged PDF” vs normal export) and see if tagging/language/title improved

Create evidence for accessibility audits: a repeatable report and a manual confirmation step

Turn it into a team process: one person runs auto checks, another confirms manual items, then save the final report text

With small tweaks you could also:

Export results to JSON/CSV

Enforce stricter scoring (right now it’s intentionally forgiving)

Add checks specific to your org (e.g., “must include contact details for accessibility help”)

How it does it (the moving parts)
1) The checklist definition (CHECKLIST)

A dictionary with items like:

id: stable identifier

category: grouping in the UI/report

description: what humans read

weight: how important it is in scoring

Some are “auto-checkable from PDF”, many are intentionally manual.

2) The scoring philosophy (supportive)

This is crucial: it is not a strict pass/fail tool.

SCORE_MAP_SUPPORTIVE = {"pass": 1.0, "partial": 0.85, "fail": 0.20}

“manual” items are excluded from scoring until the user confirms them

“unconfirmed” manual items are also excluded (so they don’t hurt you)

So the score is basically:

“Of the items we’re willing to score, how well did you do, with partial credit being generous?”

Grade bands are then mapped from the % score (A/B/C/D/E).

3) Reading the uploaded PDF (input handling)

file_to_bytes(uploaded) accepts multiple upload formats:

raw bytes

filepath string (Gradio type="filepath" uses this)

file-like object with .read()

It normalizes everything to bytes, so the rest of the pipeline is consistent.

4) Extracting signals from the PDF (extract_features)

This is the “data extraction” engine. It uses PyPDF2 and collects features such as:

Metadata / structure

Title: reader.metadata.title

Language: /Root → /Lang

Tagged PDF signal: checks whether /StructTreeRoot exists (a rough indicator of tagging)

Text presence / OCR-ish clue

Extracts text per page (page.extract_text()).

Counts pages that have at least ~20 characters of text.

Computes text_page_ratio = pages with text / total pages
This is used as a proxy for “is this mostly real text vs scanned images?”

Readability (rough, offline)

Implements syllable counting + Flesch Reading Ease + Flesch-Kincaid Grade

This is heuristic (PDF text extraction can be messy), but useful as a “clarity hint”.

Style patterns

Detects ALL CAPS paragraphs (all_caps_ratio)

Detects acronyms (\b[A-Z]{3,}\b)

Instruction language

Counts “click”

Counts device-neutral verbs (“select/tap/choose/press/activate”)

Links

Counts URL-like strings

Counts “click here”

Images

Estimates image count by scanning PDF page XObjects with subtype /Image

All of that is returned as one feat dictionary.

5) Converting features into checklist results (static_evaluate)

This function walks every checklist item and assigns:

status: pass, partial, fail, manual, not_applicable

reason: a human-readable explanation

For example:

doc_title_present passes if metadata title exists and isn’t “Untitled”

doc_language_present passes if /Lang exists

doc_tagged_pdf passes if /StructTreeRoot exists

doc_text_extractable is pass/partial/fail based on text_page_ratio

readability becomes pass/partial/fail by thresholds

acronyms becomes manual (it can detect them, but can’t verify they’re explained)

most design/interaction items remain manual because PDFs can’t reliably prove them

So: features → checklist statuses + reasons.

6) Scoring (compute_score_supportive)

It only includes statuses in {pass, partial, fail} by default.
Manual/unconfirmed/not_applicable don’t affect the score.

It computes a weighted % and maps it to A–E.

7) Generating the written report

analyze_course() builds Markdown sections like:

supportive score + grade

what was measured (pages, text ratio, image estimate, etc.)

glossary explaining key terms

top “next steps” (prioritised by failed/partial and weight)

lists of passes/partials/fails

explains that manual checks come next

It also creates an internal state_obj (JSON string) stored in gr.State, containing:

the evaluation item list

mapping between displayed checkbox labels and internal item IDs

how many manual items exist

8) Manual confirmation and final report

update_manual_progress() just updates “X / Y confirmed”.

finalize_grade():

converts checked labels → item IDs

turns checked manual items into pass

turns unchecked manual items into unconfirmed (excluded from scoring)

recomputes the score and adds a “confidence level” based on how many manual items you confirmed

So the final output is:

“Auto checks + the manual checks you explicitly confirmed.”
