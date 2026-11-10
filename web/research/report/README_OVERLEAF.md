# Overleaf upload

The latest report is already updated in the [existing Overleaf project](https://www.overleaf.com/project/6af1851e5c469ea8674182d0), with a clean online compilation (0 errors and 0 warnings). `CS3263_Project_Report.pdf` is the downloaded online result.

For a new project, unzip/import `CS3263_report_overleaf.zip`. For an existing project, upload the TeX files at its root and assets into `figures/`, overwriting the matching files; uploading a ZIP to an existing project stores it without extraction. Set `main.tex` as the main document. Use pdfLaTeX or XeLaTeX; only standard TeX packages are used. Bibliography entries are included in the source, so no separate BibTeX run is needed.

The revised PDF contains 11 physical pages: title, **9 report-body pages**, one reference page. The body uses the course format: single column, single spacing, 11pt, one-inch margins. It includes five figures (task, architecture, and three actual product screenshots), requirement-specific quantitative tables and an explicitly pending qualitative result table. The latest presentation instruction is a video of at most 10 minutes; the storyboard targets 9:20 and omits a separate Responsible AI section.

Include all files from the ZIP, including `body.tex`, `academic_results.tex`, `temporal_results.tex`, `qualitative_results.tex` and `figures/`. Set `main.tex` as the main document. The prebuilt figure PDFs/PNGs work directly in Overleaf; the capture/diagram scripts are only needed to regenerate assets. `results.tex` from the old upload is no longer used.

The numerical tables are aggregated from saved real plans using `build_requirement_tables.py`; no new model calls are made. Academic and temporal checks are separate. Service/format failures remain unscored. TBC in the qualitative table is an explicit placeholder, not a measured score. The online source files were downloaded again and verified byte-for-byte against the uploaded source and assets.

Human review before submission: validate the final claims, official sources and scope of curriculum rules, author information, contribution statement and AI disclosure. Keep raw experimental material in the separate supplementary appendix; do not place substantive discussion outside the ten-page body limit.
