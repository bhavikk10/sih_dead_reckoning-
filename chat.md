# Understand the document

> understand the doc completely, no coding required

<details><summary>16 previous messages</summary>

> I’ll first locate the document in the workspace, then read it end to end and give you a clear understanding of its purpose, structure, requirements, assumptions, and any ambiguities—without changing or coding anything.
>
> <details><summary>Ran a command</summary>
>
> - Ran `rg --files`
>
> </details>
>
> I found a single Word document: `IDR_Architecture_Brief.docx`. I’m using the document-analysis skill because it preserves Word structure and supports visual verification, which matters for catching details in tables, diagrams, headers, or page layout.
>
> <details><summary>Explored a file, ran 3 commands</summary>
>
> <details><summary>Explored a file</summary>
>
> - Read `C:/Users/bhavi/.codex/plugins/cache/openai-primary-runtime/documents/26.826.12353/skills/documents/SKILL.md`
>
> </details>
>
> - Ran ``$p='C:\Users\bhavi\.codex\plugins\cache\openai-primary-runtime\documents\26.826.12353\skills\documents\SKILL.md'; $lines=Get-Content $p; $lines[0..199] -join "`n"``
>
> - Ran ``$p='C:\Users\bhavi\.codex\plugins\cache\openai-primary-runtime\documents\26.826.12353\skills\documents\SKILL.md'; $lines=Get-Content $p; $lines[200..399] -join "`n"``
>
> - Ran ``$p='C:\Users\bhavi\.codex\plugins\cache\openai-primary-runtime\documents\26.826.12353\skills\documents\SKILL.md'; $lines=Get-Content $p; $lines[400..($lines.Count-1)] -join "`n"``
>
> <details><summary>Explored a file</summary>
>
> - Read `C:/Users/bhavi/.codex/plugins/cache/openai-primary-runtime/documents/26.826.12353/skills/documents/tasks/read_review.md`
>
> </details>
>
> </details>
>
> I’m now checking both layers of the brief: the actual text and document structure, plus the rendered pages. That lets me distinguish what the architecture says from what may only be implied by a diagram or layout. I’m keeping this strictly read-only; the original file will not be altered.
>
> <details><summary>Ran a command</summary>
>
> - Ran `$reviewDir = Join-Path $env:TEMP ('idr_review_' + [guid]::NewGuid().ToString('N')); New-Item -ItemType Directory -Path $reviewDir | Out-Null; & 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' 'C:\Users\bhavi\.codex\plugins\cache\openai-primary-runtime\documents\26.826.12353\skills\documents\render_docx.py' 'E:\dead reckoning\IDR_Architecture_Brief.docx' --output_dir $reviewDir --emit_pdf; Write-Output "REVIEW_DIR=$reviewDir"; Get-ChildItem -LiteralPath $reviewDir | Select-Object Name,Length`
>
> </details>
>
> The packaged renderer hit a missing local conversion binary, so I’m using the skill’s read-only fallback: inspect the Word structure directly and separately verify any embedded diagrams/media. This does not affect the document, and it still lets me trace every section and requirement.
>
> <details><summary>Ran 5 commands</summary>
>
> - Ran `$code = @'
> from docx import Document
> from docx.oxml.ns import qn
> from docx.table import Table
> from docx.text.paragraph import Paragraph
> p = r"E:\dead reckoning\IDR_Architecture_Brief.docx"
> doc = Document(p)
> cp = doc.core_properties
> print("CORE")
> print("title=", cp.title)
> print("subject=", cp.subject)
> print("author=", cp.author)
> print("created=", cp.created)
> print("modified=", cp.modified)
> print("revision=", cp.revision)
> print("\nSECTIONS", len(doc.sections))
> for i,s in enumerate(doc.sections,1):
>     print(f"section {i}: page={s.page_width}x{s.page_height}, margins={s.top_margin},{s.right_margin},{s.bottom_margin},{s.left_margin}")
> print("\nBODY IN DOCUMENT ORDER")
> bi=0
> for child in doc.element.body.iterchildren():
>     if child.tag == qn('w:p'):
>         para = Paragraph(child, doc)
>         txt = para.text.strip()
>         if txt:
>             bi += 1
>             print(f"P{bi} [{para.style.name}] {txt}")
>     elif child.tag == qn('w:tbl'):
>         table = Table(child, doc)
>         bi += 1
>         print(f"TABLE{bi} rows={len(table.rows)} cols={len(table.columns)}")
>         for ri,row in enumerate(table.rows,1):
>             cells = [' '.join(c.text.split()) for c in row.cells]
>             print(f"  R{ri}: " + " || ".join(cells))
> for si,s in enumerate(doc.sections,1):
>     print(f"\nHEADER section {si}")
>     for para in s.header.paragraphs:
>         if para.text.strip(): print(f"[{para.style.name}] {para.text}")
>     print(f"FOOTER section {si}")
>     for para in s.footer.paragraphs:
>         if para.text.strip(): print(f"[{para.style.name}] {para.text}")
> print("\nCOUNTS")
> print("paragraphs",len(doc.paragraphs),"tables",len(doc.tables),"inline_shapes",len(doc.inline_shapes))
> '@; & 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c $code`
> - Ran `$code = @'
> from docx import Document
> from docx.oxml.ns import qn
> from docx.table import Table
> from docx.text.paragraph import Paragraph
> p = r"E:\dead reckoning\IDR_Architecture_Brief.docx"
> doc = Document(p)
> cp = doc.core_properties
> print("CORE")
> print("title=", cp.title)
> print("subject=", cp.subject)
> print("author=", cp.author)
> print("created=", cp.created)
> print("modified=", cp.modified)
> print("revision=", cp.revision)
> print("\nSECTIONS", len(doc.sections))
> for i,s in enumerate(doc.sections,1):
>     print(f"section {i}: page={s.page_width}x{s.page_height}, margins={s.top_margin},{s.right_margin},{s.bottom_margin},{s.left_margin}")
> print("\nBODY IN DOCUMENT ORDER")
> bi=0
> for child in doc.element.body.iterchildren():
>     if child.tag == qn('w:p'):
>         para = Paragraph(child, doc)
>         txt = para.text.strip()
>         if txt:
>             bi += 1
>             style = para.style.name if para.style is not None else '(none)'
>             print(f"P{bi} [{style}] {txt}")
>     elif child.tag == qn('w:tbl'):
>         table = Table(child, doc)
>         bi += 1
>         print(f"TABLE{bi} rows={len(table.rows)} cols={len(table.columns)}")
>         for ri,row in enumerate(table.rows,1):
>             cells = [' '.join(c.text.split()) for c in row.cells]
>             print(f"  R{ri}: " + " || ".join(cells))
> for si,s in enumerate(doc.sections,1):
>     print(f"\nHEADER section {si}")
>     for para in s.header.paragraphs:
>         if para.text.strip():
>             style=para.style.name if para.style is not None else '(none)'
>             print(f"[{style}] {para.text}")
>     print(f"FOOTER section {si}")
>     for para in s.footer.paragraphs:
>         if para.text.strip():
>             style=para.style.name if para.style is not None else '(none)'
>             print(f"[{style}] {para.text}")
> print("\nCOUNTS")
> print("paragraphs",len(doc.paragraphs),"tables",len(doc.tables),"inline_shapes",len(doc.inline_shapes))
> '@; & 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c $code`
> - Ran `$env:PYTHONIOENCODING='utf-8'; $code = @'
> from docx import Document
> from docx.oxml.ns import qn
> from docx.table import Table
> from docx.text.paragraph import Paragraph
> p = r"E:\dead reckoning\IDR_Architecture_Brief.docx"
> doc = Document(p)
> bi=0
> for child in doc.element.body.iterchildren():
>     if child.tag == qn('w:p'):
>         para = Paragraph(child, doc)
>         txt = para.text.strip()
>         if txt:
>             bi += 1
>             style = para.style.name if para.style is not None else '(none)'
>             print(f"P{bi} [{style}] {txt}")
>     elif child.tag == qn('w:tbl'):
>         table = Table(child, doc)
>         bi += 1
>         print(f"TABLE{bi} rows={len(table.rows)} cols={len(table.columns)}")
>         for ri,row in enumerate(table.rows,1):
>             cells = [' '.join(c.text.split()) for c in row.cells]
>             print(f"  R{ri}: " + " || ".join(cells))
> '@; & 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c $code`
> - Ran `$candidates = @((Get-Command soffice.exe -ErrorAction SilentlyContinue).Source,(Get-Command WINWORD.EXE -ErrorAction SilentlyContinue).Source,'C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE','C:\Program Files\LibreOffice\program\soffice.exe'); $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique; $env:PYTHONIOENCODING='utf-8'; $code=@'
> from zipfile import ZipFile
> from lxml import etree
> p=r"E:\dead reckoning\IDR_Architecture_Brief.docx"
> with ZipFile(p) as z:
>     names=set(z.namelist())
>     print("PACKAGE_PARTS", len(names))
>     for group,prefix in [("media","word/media/"),("charts","word/charts/"),("embeddings","word/embeddings/")]:
>         items=sorted(n for n in names if n.startswith(prefix))
>         print(group, len(items), items)
>     for part in ["word/comments.xml","word/footnotes.xml","word/endnotes.xml","word/header1.xml","word/footer1.xml"]:
>         print(part, part in names)
>     xml=etree.fromstring(z.read("word/document.xml"))
>     ns={"w":"http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
>     print("tracked_insertions",len(xml.xpath('.//w:ins',namespaces=ns)))
>     print("tracked_deletions",len(xml.xpath('.//w:del',namespaces=ns)))
>     print("comment_refs",len(xml.xpath('.//w:commentReference',namespaces=ns)))
>     print("drawings",len(xml.xpath('.//w:drawing',namespaces=ns)))
>     print("page_breaks",len(xml.xpath('.//w:br[@w:type="page"]',namespaces=ns)))
> '@; & 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c $code`
> - Ran `& 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "import importlib.util; print('fitz',bool(importlib.util.find_spec('fitz'))); print('pymupdf',bool(importlib.util.find_spec('pymupdf'))); print('pypdfium2',bool(importlib.util.find_spec('pypdfium2'))); print('PIL',bool(importlib.util.find_spec('PIL')))"`
>
> </details>
>
> Microsoft Word is available locally, so I can complete the visual check after all: I’ll open the brief read-only, export a temporary PDF, and inspect each rendered page. The original `.docx` remains untouched.
>
> <details><summary>Ran a command</summary>
>
> - Ran `$reviewDir = Join-Path $env:TEMP ('idr_word_review_' + [guid]::NewGuid().ToString('N')); New-Item -ItemType Directory -Path $reviewDir | Out-Null; $pdf = Join-Path $reviewDir 'IDR_Architecture_Brief.pdf'; $word = $null; $doc = $null; try { $word = New-Object -ComObject Word.Application; $word.Visible = $false; $word.DisplayAlerts = 0; $doc = $word.Documents.Open('E:\dead reckoning\IDR_Architecture_Brief.docx',$false,$true,$false); $doc.ExportAsFixedFormat($pdf,17); } finally { if ($doc) { $doc.Close(0) }; if ($word) { $word.Quit() }; if ($doc) { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($doc) | Out-Null }; if ($word) { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null }; [gc]::Collect(); [gc]::WaitForPendingFinalizers() }; $env:PYTHONIOENCODING='utf-8'; $code=@'
> import pypdfium2 as pdfium, os, sys
> pdf_path=sys.argv[1]
> out=sys.argv[2]
> pdf=pdfium.PdfDocument(pdf_path)
> print("pages",len(pdf))
> for i,page in enumerate(pdf):
>     img=page.render(scale=2.0).to_pil()
>     path=os.path.join(out,f"page-{i+1}.png")
>     img.save(path)
>     print(os.path.basename(path), img.size)
> '@; & 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c $code $pdf $reviewDir; Write-Output "REVIEW_DIR=$reviewDir"; Get-ChildItem -LiteralPath $reviewDir | Select-Object Name,Length`
>
> </details>
>
> Viewed 4 images
>
> Viewed 4 images
>
> Viewed 4 images
>
> Viewed 2 images
>
> I’ve finished the content and page-by-page pass. The proposal is coherent at the high level, but it is still an architecture brief—not yet an implementation specification. I’m consolidating the intended system, the decisions already made, and the few dependency gaps that the team must resolve before building.
>
> <details><summary>Ran a command</summary>
>
> - Ran `$env:PYTHONIOENCODING='utf-8'; $code=@'
> from zipfile import ZipFile
> from lxml import etree
> p=r"E:\dead reckoning\IDR_Architecture_Brief.docx"
> ns={"w":"http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
> with ZipFile(p) as z:
>     for part,label,item in [("word/comments.xml","comments","comment"),("word/footnotes.xml","footnotes","footnote"),("word/endnotes.xml","endnotes","endnote")]:
>         root=etree.fromstring(z.read(part))
>         nodes=root.xpath(f'.//w:{item}',namespaces=ns)
>         real=[]
>         for n in nodes:
>             ident=n.get('{%s}id'%ns['w'])
>             txt=''.join(n.xpath('.//w:t/text()',namespaces=ns)).strip()
>             if ident not in ('-1','0') or txt:
>                 real.append((ident,txt))
>         print(label,len(real),real)
> '@; & 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c $code`
>
> </details>
</details>

I’ve read and visually inspected the complete document. No coding or file changes were made.

The brief proposes a phone-based dead-reckoning navigation system for GNSS outages, targeting less than 10% positional drift over the distance travelled. It must produce two deliverables: a mobile app using only phone sensors and a reusable edge engine capable of accepting higher-rate external IMUs. Initial screening evidence must use IO-VNBD data. :codex-file-citation{path="E:/dead reckoning/IDR_Architecture_Brief.docx" purpose="source" artifact_kind="document" page_number="2"}

The intended pipeline is:

`Sensors → orientation/calibration → gravity removal → learned speed + uncertainty + road context → EKF fusion → HMM map matching → smooth GNSS handoff`

The fusion filter is the architectural centre and sole position authority. The AI components supply measurements or confidence information; they do not independently calculate the final location. :codex-file-citation{path="E:/dead reckoning/IDR_Architecture_Brief.docx" purpose="source" artifact_kind="document" page_number="3"}

The deterministic backbone consists of:

- Accelerometer and gyroscope as primary sensors; magnetometer heading is intentionally distrusted in vehicles.
- Continuous phone-to-vehicle orientation calibration.
- Gravity removal after coordinate-frame alignment.
- Non-holonomic constraints that approximately force sideways and vertical velocity to zero.
- EKF as the default fusion method, with UKF as a fallback.
- HMM/Viterbi map matching against the road network.
- Gradual GNSS/dead-reckoning blending based on signal quality. :codex-file-citation{path="E:/dead reckoning/IDR_Architecture_Brief.docx" purpose="source" artifact_kind="document" page_number="4"} :codex-file-citation{path="E:/dead reckoning/IDR_Architecture_Brief.docx" purpose="source" artifact_kind="document" page_number="5"}

The three AI engines are:

1. **Velocity engine:** A small 1D-CNN or GRU predicts forward speed from a 1–2 second IMU window, replacing unstable double integration. Transformers are explicitly rejected as unnecessarily heavy. :codex-file-citation{path="E:/dead reckoning/IDR_Architecture_Brief.docx" purpose="source" artifact_kind="document" page_number="7"}

2. **Uncertainty engine:** Starts with heuristic covariance scaling, then adds a heteroscedastic output head that predicts mean and log-variance. A differentiable EKF is only a stretch goal. :codex-file-citation{path="E:/dead reckoning/IDR_Architecture_Brief.docx" purpose="source" artifact_kind="document" page_number="8"}

3. **Road-context engine:** Supplies a plausible speed range based on road characteristics, historical traffic patterns, and recent journey history. It is a soft validation prior, not a replacement for sensor-derived speed. Live traffic is optional; the core must operate entirely offline. :codex-file-citation{path="E:/dead reckoning/IDR_Architecture_Brief.docx" purpose="source" artifact_kind="document" page_number="9"}

The data strategy combines IO-VNBD for the first two engines with SUMO-generated Indian traffic, global trajectory datasets, limited Indian traffic datasets, and OpenStreetMap for the road-context layer and map graph. :codex-file-citation{path="E:/dead reckoning/IDR_Architecture_Brief.docx" purpose="source" artifact_kind="document" page_number="10"} :codex-file-citation{path="E:/dead reckoning/IDR_Architecture_Brief.docx" purpose="source" artifact_kind="document" page_number="11"}

For the application, the document recommends Flutter, with native Kotlin as the strongest alternative and React Native as the weakest fit. Offline mapping should begin with raster MBTiles for the demo, then move to MapLibre vector tiles. iOS is considered optional until the Android-oriented primary demo works. :codex-file-citation{path="E:/dead reckoning/IDR_Architecture_Brief.docx" purpose="source" artifact_kind="document" page_number="12"} :codex-file-citation{path="E:/dead reckoning/IDR_Architecture_Brief.docx" purpose="source" artifact_kind="document" page_number="13"}

The important unresolved architecture points are:

- Road context needs the current road segment, but map matching occurs after fusion—creating a dependency loop that needs an explicit solution.
- “Whole-path” Viterbi is not directly real-time; an incremental or sliding-window version will be required.
- It is unclear whether Engine 1 consumes raw phone-frame IMU data or calibrated, gravity-removed vehicle-frame data.
- Engine 3 has a data strategy but no chosen model, output schema, or training objective.
- The document alternates between saying there are “two” learned stages and presenting three AI engines.
- The EKF state vector, coordinate system, covariance rules, timestamps, sensor synchronization, outlier rejection, and component interfaces remain unspecified.
- The 10% drift requirement needs a formal evaluation protocol—endpoint versus trajectory error, outage lengths, device placement, road types, and repeated-run statistics.
- The higher-rate edge-engine deliverable is acknowledged but substantially less defined than the phone application.
- Dataset generalization across phones, mounting positions, vehicles, countries, and road surfaces is a major technical risk.
- Road context must be gated carefully so an incorrect traffic prior cannot pull the fusion estimate away from valid sensor evidence.

The document itself recognizes six team decisions: EKF versus UKF, first Indian city, data-collection timing, whether to attempt differentiable EKF, Flutter versus Kotlin and MapLibre ownership, and the implementation depth of the edge engine. :codex-file-citation{path="E:/dead reckoning/IDR_Architecture_Brief.docx" purpose="source" artifact_kind="document" page_number="14"}

Overall, it is a strong onboarding and solution-direction brief. It explains the concept and trade-offs clearly, but it is not yet detailed enough to serve as a build-ready technical specification. Also, its external claims and dataset/API references are uncited and have not been independently verified.

> so in this, our task is the deterministic pipeline + the 2 ai engines except the velocity prediction one (so the uncertainity and 3rd one), so lets first ideate for them
>
> then,
> initialise the folder, only stubs and initialisations, and comments, for whatever we've to do

<details><summary>9 previous messages</summary>

> I’ll map the exact ownership boundary from the brief and inspect the workspace first. Since we’re planning the initialization, I’ll keep the repository untouched and use the findings to decide the module boundaries, stubs, and comments we’ll create.
>
> <details><summary>Ran a command</summary>
>
> - Ran `Get-ChildItem -Force | Select-Object Mode,Length,LastWriteTime,Name; if (Test-Path -LiteralPath '.git') { & 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe' status --short --branch } else { Write-Output 'NO_GIT_REPOSITORY' }`
>
> </details>
>
> The workspace is empty apart from the brief—there is no existing repository, language choice, or code structure to preserve. The clean ownership boundary is stages 1–3 and 7–9, plus uncertainty and road context; velocity prediction must enter through a contract owned by the other team.
>
> Three decisions materially affect the skeleton, especially because the brief’s uncertainty design assumes access to the velocity model.
>
> Your choices point to a clean design: a Python-only navigation backend, a strict adapter for the separately owned velocity predictor, a learned covariance estimator sitting between Tier 2 and Tier 3, and a hybrid rule-plus-ML road prior.
>
> I’m using the visualization skill here because the same-cycle dependency between fusion, road candidates, road context, and map matching is much easier to resolve as a data-flow diagram than as prose. This will influence the module boundaries, but it won’t create or modify repository files.
>
> Here is the architecture I’d recommend ideating around:
>
> ```mermaid
> flowchart LR
>     IMU[Phone / external IMU] --> PRE[Timestamping, calibration,\norientation, gravity removal]
>     PRE --> PROP[Error-state EKF propagation]
>     VEL[External velocity predictor] --> UQ[Learned uncertainty estimator\n+ heuristic safety bounds]
>     PRE --> UQ
>     UQ --> FUSE[EKF measurement update]
>
>     PROP --> CAND[Road-candidate generator\nfrom previous HMM belief]
>     CAND --> RC[Hybrid road-context engine\nrules + probabilistic ML]
>     RC --> FUSE
>     GNSS[GNSS + quality] --> FUSE
>     NHC[Non-holonomic constraints] --> FUSE
>
>     FUSE --> HMM[Incremental / sliding-window HMM]
>     HMM --> OUT[Navigation estimate]
>     HMM -. next-cycle road belief .-> CAND
> ```
>
> The important resolution is that road context uses the previous HMM belief and current candidate roads, then the updated fusion result advances map matching. That avoids asking the same timestep’s map-match result to exist before fusion.
>
> For uncertainty, “between Tier 2 and Tier 3” can mean a separate covariance network trained on velocity residuals, with optional trajectory-level fine-tuning through a differentiable EKF later. It remains independently owned even though the velocity model belongs to another team.
>
> That locks the technical direction well:
>
> - 15-state error-state EKF.
> - Uncertainty network trained first with Gaussian NLL, with a later differentiable-EKF fine-tuning path.
> - Road context exposes quantiles plus rule gates, but the initial scaffold deliberately does **not** choose LightGBM versus XGBoost or add either dependency. It records both options behind one model interface.
>
> I’m checking the available Python/tooling versions before asking the last repository-initialization choices.
>
> <details><summary>Ran a command</summary>
>
> - Ran `& 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' --version; foreach ($name in @('uv','poetry','ruff','mypy','pytest')) { $cmd=Get-Command $name -ErrorAction SilentlyContinue; if ($cmd) { "$name=$($cmd.Source)" } else { "$name=NOT_FOUND" } }`
>
> </details>
>
> One conflict remains to lock down: you asked to leave the road-tree implementation choice open, but also selected declaring all planned dependencies immediately. Installing both tree libraries would make the scaffold heavier and imply a comparison track; declaring neither keeps the choice genuinely open.
>
> Plan
>
> # Initialize the IDR Python Backend Skeleton
>
> ## Summary
>
> Create a Python 3.12 package named `idr_backend` containing only folders, package initializers, module docstrings, and detailed TODO comments. Do not implement algorithms, stable data types, runnable placeholders, Git initialization, or frontend code.
>
> ```mermaid
> flowchart LR
>     IMU[IMU/GNSS adapters] --> PRE[Calibration and preprocessing]
>     PRE --> EKF[15-state error-state EKF]
>     VP[External velocity predictor] --> UQ[Uncertainty engine]
>     UQ --> EKF
>     EKF --> CAND[Road candidates]
>     CAND --> RC[Rules + quantile ML]
>     RC --> EKF
>     EKF --> HMM[Incremental HMM map matching]
>     HMM --> OUT[Navigation estimate]
>     HMM -. previous belief .-> CAND
> ```
>
> ## Package Structure and Responsibilities
>
> - `src/idr_backend/sensors/`: ingestion, timestamp synchronization, unit normalization, orientation estimation, phone-to-vehicle calibration, gravity removal, and sensor-quality checks.
> - `src/idr_backend/fusion/`: 15-state error-state EKF propagation, NHC/GNSS/velocity/context measurement updates, covariance safeguards, and GNSS-aided/dead-reckoning/recovery modes.
> - `src/idr_backend/uncertainty/`: input features, heuristic safety bounds, heteroscedastic covariance model, Gaussian-NLL training, calibration, and future differentiable-EKF fine-tuning.
> - `src/idr_backend/road_context/`: OSM and journey features, deterministic bounds, quantile-model abstraction, candidate-road priors, and dataset preparation. Record LightGBM and XGBoost as unresolved alternatives.
> - `src/idr_backend/map_matching/`: offline road graph, candidate generation, transition/emission scoring, and incremental or sliding-window HMM/Viterbi.
> - `src/idr_backend/adapters/`: external velocity predictor, phone/external IMU, GNSS, OSM graph, and future frontend integration boundaries.
> - `src/idr_backend/pipeline/`: future asynchronous orchestration and next-cycle feedback from map matching to road context.
> - Add `tests/{unit,integration,fixtures}`, `configs`, `docs`, and `scripts` with explanatory README/TODO files and no executable behavior.
>
> ## Project Initialization
>
> - Add `pyproject.toml` using a `src` layout and Hatchling build backend.
> - Declare Python 3.12 and the complete planned dependency set without creating a virtual environment or lock file:
>   - Scientific/data: NumPy, SciPy, pandas, PyArrow.
>   - ML: PyTorch, scikit-learn, LightGBM, XGBoost, joblib.
>   - Geospatial: NetworkX, OSMnx, GeoPandas, Shapely, PyProj, Pyrosm.
>   - Model export/evaluation: ONNX, ONNX Runtime, Matplotlib.
>   - Configuration: Pydantic and pydantic-settings.
>   - Development: pytest, pytest-cov, Hypothesis, Ruff, and mypy.
> - Use commented TOML configuration templates for phone, external-IMU, training, and evaluation profiles.
> - Add a root README covering ownership, architecture, component status, and the explicit exclusion of velocity-model implementation and frontend work.
> - Do not initialize Git or configure a remote.
>
> ## Interfaces and Tests
>
> - Do not introduce stable public APIs yet. TODO comments will describe the future contracts: `ImuSample`, `GnssFix`, `VelocityObservation`, `UncertaintyEstimate`, `RoadContextPrior`, `RoadCandidate`, and `NavigationEstimate`.
> - Keep every package importable; avoid placeholder functions that return fabricated values or tests that fail intentionally.
> - Verify the scaffold using Python compilation, package-import smoke checks, and `pyproject.toml` parsing.
> - Document future tests for sensor gaps/frame transforms, EKF covariance validity, NHC updates, uncertainty calibration, positive variance, quantile ordering, rule gating, unseen-road behavior, HMM ambiguity, GNSS loss/recovery, and end-to-end replay.
>
> ## Assumptions
>
> - The velocity predictor is supplied by another team through an adapter; its training and inference implementation remain out of scope.
> - Uncertainty starts as a separately owned residual covariance network trained with Gaussian NLL, with differentiable-EKF trajectory fine-tuning planned later.
> - Road context will ultimately combine quantile boosted trees with deterministic rules, but LightGBM versus XGBoost remains intentionally undecided.
> - Road context uses previous HMM belief plus current candidates, avoiding a same-timestep fusion/map-matching dependency loop.
> - No datasets, trained weights, native/mobile integration, live APIs, algorithms, or frontend assets are added during initialization.
</details>

> PLEASE IMPLEMENT THIS PLAN:
> # Initialize the IDR Python Backend Skeleton
>
> ## Summary
>
> Create a Python 3.12 package named `idr_backend` containing only folders, package initializers, module docstrings, and detailed TODO comments. Do not implement algorithms, stable data types, runnable placeholders, Git initialization, or frontend code.
>
> ```mermaid
> flowchart LR
>     IMU[IMU/GNSS adapters] --> PRE[Calibration and preprocessing]
>     PRE --> EKF[15-state error-state EKF]
>     VP[External velocity predictor] --> UQ[Uncertainty engine]
>     UQ --> EKF
>     EKF --> CAND[Road candidates]
>     CAND --> RC[Rules + quantile ML]
>     RC --> EKF
>     EKF --> HMM[Incremental HMM map matching]
>     HMM --> OUT[Navigation estimate]
>     HMM -. previous belief .-> CAND
> ```
>
> ## Package Structure and Responsibilities
>
> - `src/idr_backend/sensors/`: ingestion, timestamp synchronization, unit normalization, orientation estimation, phone-to-vehicle calibration, gravity removal, and sensor-quality checks.
> - `src/idr_backend/fusion/`: 15-state error-state EKF propagation, NHC/GNSS/velocity/context measurement updates, covariance safeguards, and GNSS-aided/dead-reckoning/recovery modes.
> - `src/idr_backend/uncertainty/`: input features, heuristic safety bounds, heteroscedastic covariance model, Gaussian-NLL training, calibration, and future differentiable-EKF fine-tuning.
> - `src/idr_backend/road_context/`: OSM and journey features, deterministic bounds, quantile-model abstraction, candidate-road priors, and dataset preparation. Record LightGBM and XGBoost as unresolved alternatives.
> - `src/idr_backend/map_matching/`: offline road graph, candidate generation, transition/emission scoring, and incremental or sliding-window HMM/Viterbi.
> - `src/idr_backend/adapters/`: external velocity predictor, phone/external IMU, GNSS, OSM graph, and future frontend integration boundaries.
> - `src/idr_backend/pipeline/`: future asynchronous orchestration and next-cycle feedback from map matching to road context.
> - Add `tests/{unit,integration,fixtures}`, `configs`, `docs`, and `scripts` with explanatory README/TODO files and no executable behavior.
>
> ## Project Initialization
>
> - Add `pyproject.toml` using a `src` layout and Hatchling build backend.
> - Declare Python 3.12 and the complete planned dependency set without creating a virtual environment or lock file:
>   - Scientific/data: NumPy, SciPy, pandas, PyArrow.
>   - ML: PyTorch, scikit-learn, LightGBM, XGBoost, joblib.
>   - Geospatial: NetworkX, OSMnx, GeoPandas, Shapely, PyProj, Pyrosm.
>   - Model export/evaluation: ONNX, ONNX Runtime, Matplotlib.
>   - Configuration: Pydantic and pydantic-settings.
>   - Development: pytest, pytest-cov, Hypothesis, Ruff, and mypy.
> - Use commented TOML configuration templates for phone, external-IMU, training, and evaluation profiles.
> - Add a root README covering ownership, architecture, component status, and the explicit exclusion of velocity-model implementation and frontend work.
> - Do not initialize Git or configure a remote.
>
> ## Interfaces and Tests
>
> - Do not introduce stable public APIs yet. TODO comments will describe the future contracts: `ImuSample`, `GnssFix`, `VelocityObservation`, `UncertaintyEstimate`, `RoadContextPrior`, `RoadCandidate`, and `NavigationEstimate`.
> - Keep every package importable; avoid placeholder functions that return fabricated values or tests that fail intentionally.
> - Verify the scaffold using Python compilation, package-import smoke checks, and `pyproject.toml` parsing.
> - Document future tests for sensor gaps/frame transforms, EKF covariance validity, NHC updates, uncertainty calibration, positive variance, quantile ordering, rule gating, unseen-road behavior, HMM ambiguity, GNSS loss/recovery, and end-to-end replay.
>
> ## Assumptions
>
> - The velocity predictor is supplied by another team through an adapter; its training and inference implementation remain out of scope.
> - Uncertainty starts as a separately owned residual covariance network trained with Gaussian NLL, with differentiable-EKF trajectory fine-tuning planned later.
> - Road context will ultimately combine quantile boosted trees with deterministic rules, but LightGBM versus XGBoost remains intentionally undecided.
> - Road context uses previous HMM belief plus current candidates, avoiding a same-timestep fusion/map-matching dependency loop.
> - No datasets, trained weights, native/mobile integration, live APIs, algorithms, or frontend assets are added during initialization.

<details><summary>6 previous messages</summary>

> I’m creating the Python-only scaffold exactly as specified: documentation-first packages and configuration templates, with no algorithms, model code, Git repository, frontend, data, or environment installation. Afterward I’ll verify syntax, importability, and project metadata.
>
> <details><summary>Ran a command</summary>
>
> - Ran `Get-ChildItem -Force | Select-Object Mode,Length,Name; if (Test-Path -LiteralPath 'pyproject.toml') { Write-Output 'PYPROJECT_EXISTS' } else { Write-Output 'NO_PYPROJECT' }; if (Test-Path -LiteralPath '.git') { Write-Output 'GIT_EXISTS' } else { Write-Output 'NO_GIT' }`
>
> </details>
>
> The workspace is still clean—only the source brief exists, with no project metadata or Git repository. I’m now adding the scaffold files in two batches: first the project metadata, documentation, configuration, test, and script placeholders; then the source-package layout.
>
> <details><summary>Created 66 files</summary>
>
> - Wrote `./.gitignore` (+19 -0)
> - Wrote `./README.md` (+54 -0)
> - Wrote `./configs/README.md` (+10 -0)
> - Wrote `./configs/evaluation.toml` (+13 -0)
> - Wrote `./configs/external_imu.toml` (+11 -0)
> - Wrote `./configs/phone.toml` (+12 -0)
> - Wrote `./configs/training.toml` (+13 -0)
> - Wrote `./docs/README.md` (+10 -0)
> - Wrote `./docs/architecture.md` (+34 -0)
> - Wrote `./docs/decisions.md` (+25 -0)
> - Wrote `./docs/validation_plan.md` (+28 -0)
> - Wrote `./pyproject.toml` (+56 -0)
> - Wrote `./scripts/README.md` (+9 -0)
> - Wrote `./scripts/evaluate.py` (+1 -0)
> - Wrote `./scripts/replay.py` (+1 -0)
> - Wrote `./scripts/train_road_context.py` (+1 -0)
> - Wrote `./scripts/train_uncertainty.py` (+1 -0)
> - Wrote `./src/idr_backend/__init__.py` (+6 -0)
> - Wrote `./tests/README.md` (+11 -0)
> - Wrote `./tests/fixtures/README.md` (+4 -0)
> - Wrote `./tests/integration/README.md` (+5 -0)
> - Wrote `./tests/unit/README.md` (+5 -0)
> - Wrote `./src/idr_backend/fusion/__init__.py` (+5 -0)
> - Wrote `./src/idr_backend/fusion/constraints.py` (+8 -0)
> - Wrote `./src/idr_backend/fusion/covariance.py` (+8 -0)
> - Wrote `./src/idr_backend/fusion/measurements.py` (+8 -0)
> - Wrote `./src/idr_backend/fusion/modes.py` (+8 -0)
> - Wrote `./src/idr_backend/fusion/propagation.py` (+8 -0)
> - Wrote `./src/idr_backend/fusion/state.py` (+8 -0)
> - Wrote `./src/idr_backend/road_context/__init__.py` (+5 -0)
> - Wrote `./src/idr_backend/road_context/datasets.py` (+8 -0)
> - Wrote `./src/idr_backend/road_context/features.py` (+8 -0)
> - Wrote `./src/idr_backend/road_context/priors.py` (+8 -0)
> - Wrote `./src/idr_backend/road_context/quantile_model.py` (+8 -0)
> - Wrote `./src/idr_backend/road_context/rules.py` (+8 -0)
> - Wrote `./src/idr_backend/sensors/__init__.py` (+5 -0)
> - Wrote `./src/idr_backend/sensors/calibration.py` (+8 -0)
> - Wrote `./src/idr_backend/sensors/gravity_removal.py` (+8 -0)
> - Wrote `./src/idr_backend/sensors/ingestion.py` (+8 -0)
> - Wrote `./src/idr_backend/sensors/normalization.py` (+8 -0)
> - Wrote `./src/idr_backend/sensors/orientation.py` (+8 -0)
> - Wrote `./src/idr_backend/sensors/quality.py` (+8 -0)
> - Wrote `./src/idr_backend/sensors/synchronization.py` (+8 -0)
> - Wrote `./src/idr_backend/uncertainty/__init__.py` (+5 -0)
> - Wrote `./src/idr_backend/uncertainty/calibration.py` (+8 -0)
> - Wrote `./src/idr_backend/uncertainty/differentiable_ekf.py` (+8 -0)
> - Wrote `./src/idr_backend/uncertainty/features.py` (+9 -0)
> - Wrote `./src/idr_backend/uncertainty/heuristics.py` (+9 -0)
> - Wrote `./src/idr_backend/uncertainty/losses.py` (+8 -0)
> - Wrote `./src/idr_backend/uncertainty/model.py` (+8 -0)
> - Wrote `./src/idr_backend/uncertainty/training.py` (+8 -0)
> - Wrote `./src/idr_backend/adapters/__init__.py` (+5 -0)
> - Wrote `./src/idr_backend/adapters/frontend.py` (+8 -0)
> - Wrote `./src/idr_backend/adapters/gnss.py` (+8 -0)
> - Wrote `./src/idr_backend/adapters/imu.py` (+8 -0)
> - Wrote `./src/idr_backend/adapters/osm.py` (+8 -0)
> - Wrote `./src/idr_backend/adapters/velocity_predictor.py` (+8 -0)
> - Wrote `./src/idr_backend/map_matching/__init__.py` (+5 -0)
> - Wrote `./src/idr_backend/map_matching/candidates.py` (+8 -0)
> - Wrote `./src/idr_backend/map_matching/graph.py` (+8 -0)
> - Wrote `./src/idr_backend/map_matching/scoring.py` (+8 -0)
> - Wrote `./src/idr_backend/map_matching/viterbi.py` (+8 -0)
> - Wrote `./src/idr_backend/pipeline/__init__.py` (+5 -0)
> - Wrote `./src/idr_backend/pipeline/feedback.py` (+8 -0)
> - Wrote `./src/idr_backend/pipeline/orchestrator.py` (+8 -0)
> - Wrote `./src/idr_backend/pipeline/runtime.py` (+8 -0)
>
> </details>
>
> The scaffold is now in place. I’m validating only structural properties: that every placeholder module compiles and imports, the TOML metadata has the intended Python/dependency declarations, and no Git repository was created.
>
> <details><summary>Ran 2 commands</summary>
>
> - Ran `$taskPython = 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'; & $taskPython -m compileall -q src scripts; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; $env:PYTHONPATH = (Join-Path (Get-Location) 'src'); $verify = @'
> import ast
> import importlib
> import pkgutil
> import tomllib
> from pathlib import Path
>
> root = Path.cwd()
> metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
> project = metadata["project"]
> assert project["name"] == "idr-backend"
> assert project["requires-python"] == ">=3.12,<3.13"
> expected = {
>     "numpy", "scipy", "pandas", "pyarrow", "torch", "scikit-learn",
>     "lightgbm", "xgboost", "joblib", "networkx", "osmnx", "geopandas",
>     "shapely", "pyproj", "pyrosm", "onnx", "onnxruntime", "matplotlib",
>     "pydantic", "pydantic-settings",
> }
> assert expected.issubset(set(project["dependencies"]))
> assert {"pytest", "pytest-cov", "hypothesis", "ruff", "mypy"}.issubset(
>     set(project["optional-dependencies"]["dev"])
> )
>
> package = importlib.import_module("idr_backend")
> modules = [package.__name__]
> for info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
>     importlib.import_module(info.name)
>     modules.append(info.name)
>
> python_files = sorted([*Path("src").rglob("*.py"), *Path("scripts").glob("*.py")])
> for path in python_files:
>     tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
>     assert ast.get_docstring(tree), f"missing module docstring: {path}"
>
> assert not (root / ".git").exists(), "scaffold must not initialize Git"
> print(f"metadata: OK ({len(project['dependencies'])} runtime dependencies)")
> print(f"imports: OK ({len(modules)} package modules)")
> print(f"docstrings: OK ({len(python_files)} Python placeholder files)")
> print("git: absent as required")
> '@; & $taskPython -c $verify`
> - Ran `$taskPython = 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'; $verify = @'
> import ast
> import tomllib
> from pathlib import Path
>
> python_files = sorted([*Path("src").rglob("*.py"), *Path("scripts").glob("*.py")])
> definitions = []
> for path in python_files:
>     tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
>     for node in ast.walk(tree):
>         if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
>             definitions.append(f"{path}:{node.name}")
> assert not definitions, f"unexpected implementation definitions: {definitions}"
> for path in sorted(Path("configs").glob("*.toml")):
>     tomllib.loads(path.read_text(encoding="utf-8"))
> print(f"implementation definitions: none across {len(python_files)} files")
> print(f"configuration templates: OK ({len(list(Path('configs').glob('*.toml')))} TOML files)")
> '@; & $taskPython -c $verify; rg --files -g '!**/__pycache__/**' | Sort-Object`
>
> </details>
</details>

Implemented the IDR Python backend scaffold.

Key entry points:

- [Project README](</E:/dead reckoning/README.md>)
- [Project metadata and declared dependencies](</E:/dead reckoning/pyproject.toml>)
- [Architecture notes](</E:/dead reckoning/docs/architecture.md>)
- [Recorded decisions](</E:/dead reckoning/docs/decisions.md>)
- [Backend source layout](</E:/dead reckoning/src/idr_backend/__init__.py>)

It includes the deterministic pipeline, uncertainty, road-context, map-matching, adapter, and orchestration packages; commented TOML profiles; future script/test placeholders; and detailed TODO guidance throughout.

Verified:

- 49 Python placeholder modules compile and have module docstrings.
- All 45 package modules import successfully.
- `pyproject.toml` and all four TOML templates parse successfully.
- No functions or classes were added—there is no algorithmic or fake placeholder behavior.
- No Git repository, virtual environment, data, models, or dependencies were created/installed.

> okay my teammate did the velocity model at [gru\_speed\_model](gru_speed_model/) , his work is in [SIH-2-main](SIH-2-main/SIH-2-main/), evaluate it, we'll just take his main files from his folder, not everything,&#x20;
>
> and then explain the current folder strcutrure, then instead of u doing everything yourself, i wanna do it and learn, so we go file by file, we choose a file, you explain what it does, one function, its expln, another fn, then its expln and so on so that i learn as well, so you dont read the entire project in every pass as well, just the current couple of files no - strat works?

<details><summary>8 previous messages</summary>

> Yes—that workflow is ideal. I’ll first evaluate only the velocity-model folders, identify the minimal reusable files and any integration requirements, then map the current scaffold. I won’t copy anything yet; after that, we’ll work in short lessons: select one or two files, read only those, and go function by function at your pace.
>
> <details><summary>Ran a command</summary>
>
> - Ran `rg --files 'gru_speed_model' 'SIH-2-main/SIH-2-main'`
>
> </details>
>
> I found a self-contained `IOVNBD-Speed-Prediction` project plus a separate serialized `gru_speed_model` directory. I’m reading the model’s code, configuration, and recorded results—not the large raw dataset—so I can distinguish reusable inference assets from training-only material and flag integration risks.
>
> <details><summary>Explored 10 files, ran 3 commands</summary>
>
> <details><summary>Explored 4 files</summary>
>
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/requirements.txt`
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/run_pipeline.py`
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/config.py`
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/README.md`
>
> </details>
>
> - Ran `Get-Content -Raw 'SIH-2-main\SIH-2-main\IOVNBD-Speed-Prediction\results\final_results.json'; Get-Content -Raw 'SIH-2-main\SIH-2-main\IOVNBD-Speed-Prediction\results\gru_test_metrics.json'; Get-Content -Raw 'SIH-2-main\SIH-2-main\IOVNBD-Speed-Prediction\run_log.txt'`
>
> - Ran `Get-Item 'gru_speed_model','gru_speed_model\data.pkl','gru_speed_model\version' | Select-Object FullName,PSIsContainer,Length,LastWriteTime; Get-Content -Raw 'gru_speed_model\version'`
>
> - Ran `Get-ChildItem 'SIH-2-main\SIH-2-main\IOVNBD-Speed-Prediction\src' -Filter '*.py' | Select-Object Name,Length; Get-ChildItem 'SIH-2-main\SIH-2-main\IOVNBD-Speed-Prediction' -Directory | Select-Object Name; Get-ChildItem 'SIH-2-main\SIH-2-main\IOVNBD-Speed-Prediction\models','SIH-2-main\SIH-2-main\IOVNBD-Speed-Prediction\artifacts' -ErrorAction SilentlyContinue | Select-Object FullName,Length`
>
> <details><summary>Explored 6 files</summary>
>
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/preprocess.py`
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/create_sequences.py`
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/evaluate.py`
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/inspect_data.py`
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/train_model.py`
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/train_baseline.py`
>
> </details>
>
> </details>
>
> The project has a sound high-level pipeline and a real sequence-level test split, but I’ve already found two integration-critical inconsistencies: the README describes a 2-second/20-sample model and much stronger metrics, while the current configuration/run log uses a 5-second/50-sample model with 17.24 km/h test MAE. I’m checking the saved GRU artifact and the training/evaluation code next, because the scaler/model packaging determines whether we can actually reuse it.
>
> <details><summary>Ran 10 commands</summary>
>
> - Ran `$n=0; Get-Content 'SIH-2-main\SIH-2-main\IOVNBD-Speed-Prediction\src\train_model.py' | ForEach-Object { $n++; '{0,4}: {1}' -f $n, $_ }`
> - Ran `$n=0; Get-Content 'SIH-2-main\SIH-2-main\IOVNBD-Speed-Prediction\src\evaluate.py' | ForEach-Object { $n++; '{0,4}: {1}' -f $n, $_ }`
> - Ran `$taskPython = 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'; $code=@'
> from pathlib import Path
> import pickletools
> p=Path("gru_speed_model/data.pkl")
> raw=p.read_bytes()
> print("bytes",len(raw))
> for i, (op, arg, pos) in enumerate(pickletools.genops(raw)):
>     print(f"{pos:04d} {op.name:<20} {arg!r}")
>     if i >= 120:
>         break
> '@; & $taskPython -c $code`
> - Ran `$taskPython = 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'; $env:PYTHONPATH = (Resolve-Path 'SIH-2-main\SIH-2-main\IOVNBD-Speed-Prediction\src'); & $taskPython -m py_compile 'SIH-2-main\SIH-2-main\IOVNBD-Speed-Prediction\src\config.py' 'SIH-2-main\SIH-2-main\IOVNBD-Speed-Prediction\src\preprocess.py' 'SIH-2-main\SIH-2-main\IOVNBD-Speed-Prediction\src\create_sequences.py' 'SIH-2-main\SIH-2-main\IOVNBD-Speed-Prediction\src\train_model.py' 'SIH-2-main\SIH-2-main\IOVNBD-Speed-Prediction\src\train_baseline.py' 'SIH-2-main\SIH-2-main\IOVNBD-Speed-Prediction\src\evaluate.py' 'SIH-2-main\SIH-2-main\IOVNBD-Speed-Prediction\src\inspect_data.py'; if ($LASTEXITCODE -eq 0) { 'syntax: OK' }`
> - Ran `$taskPython = 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'; $code=@'
> from pathlib import Path
> import pickletools
> for op, arg, pos in pickletools.genops(Path("gru_speed_model/data.pkl").read_bytes()):
>     if isinstance(arg, str):
>         print(f"{pos:04d} {op.name}: {arg}")
> '@; & $taskPython -c $code`
> - Ran `$taskPython = 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'; $code=@'
> import torch
> p="gru_speed_model"
> checkpoint=torch.load(p, map_location="cpu", weights_only=True)
> print("keys",sorted(checkpoint))
> for key in ("n_features","hidden_size","num_layers","dropout","window_size"):
>     print(f"{key}={checkpoint.get(key)!r}")
> print("state_shapes")
> for name, tensor in checkpoint["model_state_dict"].items():
>     print(name,tuple(tensor.shape),tensor.dtype,tensor.device)
> '@; & $taskPython -c $code`
> - Ran `$taskPython = 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'; $code=@'
> from pathlib import Path
> import pickletools
> for op, arg, pos in pickletools.genops(Path("gru_speed_model/data.pkl").read_bytes()):
>     if pos >= 1260:
>         print(f"{pos:04d} {op.name:<20} {arg!r}")
> '@; & $taskPython -c $code`
> - Ran `$cmd=Get-Command python -ErrorAction SilentlyContinue; if ($cmd) { $cmd | Format-List Source,Version,CommandType }; if (Test-Path -LiteralPath 'E:\Python\python.exe') { 'E_PYTHON_EXISTS'; & 'E:\Python\python.exe' --version; & 'E:\Python\python.exe' -c "import torch; print(torch.__version__)" } else { 'E_PYTHON_MISSING' }`
> - Ran `Get-Command python -All | Select-Object Source; & 'E:\Python\python.exe' -c "import sys; print(sys.version); import torch; print(torch.__version__)"`
> - Ran `Get-ChildItem -LiteralPath 'gru_speed_model' -Recurse -Force | Select-Object FullName,PSIsContainer,Length; $magic = [System.IO.File]::ReadAllBytes((Resolve-Path 'gru_speed_model\data.pkl'))[0..3] -join ' '; "data.pkl_magic=$magic"`
>
> </details>
>
> The evaluation is complete. The GRU is a usable research prototype and should be integrated only as a noisy speed measurement—not treated as truth—because its recorded held-out test error is 17.24 km/h MAE with an 87.1 km/h worst-case miss. I’m confirming the exact review locations so the findings are easy to act on when you and your teammate clean up the reusable slice.
>
> <details><summary>Ran 4 commands</summary>
>
> - Ran `$n=0; Get-Content 'SIH-2-main\SIH-2-main\IOVNBD-Speed-Prediction\src\config.py' | ForEach-Object { $n++; if ($n -ge 60 -and $n -le 95) { '{0,4}: {1}' -f $n, $_ } }`
> - Ran `$n=0; Get-Content 'SIH-2-main\SIH-2-main\IOVNBD-Speed-Prediction\src\create_sequences.py' | ForEach-Object { $n++; if ($n -ge 95 -and $n -le 160) { '{0,4}: {1}' -f $n, $_ } }`
> - Ran `$n=0; Get-Content 'SIH-2-main\SIH-2-main\IOVNBD-Speed-Prediction\src\preprocess.py' | ForEach-Object { $n++; if ($n -ge 45 -and $n -le 80) { '{0,4}: {1}' -f $n, $_ } }`
> - Ran `$n=0; Get-Content 'SIH-2-main\SIH-2-main\IOVNBD-Speed-Prediction\src\config.py' | ForEach-Object { $n++; if ($n -ge 94 -and $n -le 118) { '{0,4}: {1}' -f $n, $_ } }`
>
> </details>
</details>

Yes—this learning strategy works. We’ll only open the file(s) we explicitly choose, explain one class/function at a time, then pause for you to ask questions or write the next part. I won’t re-read the rest of the project unless the selected code directly depends on it.

## Evaluation: velocity model

It’s a legitimate prototype worth integrating as a **noisy velocity measurement** for the EKF, but it is not integration-ready yet.

The actual saved GRU architecture is:

- Input: 50 samples × 6 raw IMU channels at 10 Hz = a 5-second window
- GRU: 2 layers, hidden size 64, dropout 0.2
- Head: `64 → 32 → 1`
- Output: standardized vehicle speed, which must be inverse-transformed back to km/h

The recorded multi-sequence test result is **17.24 km/h MAE**, **23.02 km/h RMSE**, **R² 0.267**, with a worst error of **87.1 km/h**. It slightly beats the random-forest baseline, but it must be treated as uncertain and gated by our uncertainty engine—not trusted as direct truth.

The README is outdated: it claims a 2-second/20-step model and 10.48 km/h MAE, while the current code, checkpoint, and run log use 5 seconds/50 steps and the weaker 17.24 km/h result.

Most importantly: the model needs both its feature scaler and target scaler. The checkpoint currently available in [`gru_speed_model`](</E:/dead reckoning/gru_speed_model>) contains only weights and architecture metadata; it is an unpacked PyTorch archive, not a directly loadable `.pt` file. The teammate project also has no `models/` or `artifacts/` folder to supply the missing scalers.

Before reuse, obtain only:

1. The original `gru_speed_model.pt` checkpoint—or reconstruct a valid `.pt` file from the existing archive.
2. `feature_scaler.joblib`
3. `target_scaler.joblib`
4. The run’s `config.json` or equivalent manifest: feature order, units, 10 Hz input rate, 50-sample window, output units, and model version.

Do not copy the raw data, processed data, plots, baseline model, or full training pipeline.

The one source fragment worth adapting is the `GRUSpeedRegressor` class in [`train_model.py`](</E:/dead reckoning/SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/train_model.py:46>). We should move only that architecture into our future velocity adapter, with a clean load/inference wrapper.

Integration detail: the GRU was trained on **raw phone-axis accelerometer and gyroscope data**, including gravity—not on our calibrated, gravity-removed vehicle-frame signals. Our adapter must therefore maintain a separate raw-IMU buffer for this model, while the deterministic pipeline processes the calibrated stream independently.

## Current workspace structure

```text
dead reckoning/
├─ IDR_Architecture_Brief.docx     # Original architecture brief
├─ README.md                       # Our backend ownership and boundaries
├─ pyproject.toml                  # Python 3.12 project/dependency declaration
├─ src/idr_backend/                # Our empty, documented backend scaffold
│  ├─ sensors/                     # Future preprocessing and calibration
│  ├─ fusion/                      # Future 15-state error-state EKF
│  ├─ uncertainty/                 # Future learned covariance engine
│  ├─ road_context/                # Future rules + quantile-model engine
│  ├─ map_matching/                # Future incremental HMM/Viterbi
│  ├─ adapters/                    # Future velocity, IMU, GNSS, OSM bridges
│  └─ pipeline/                    # Future orchestration and feedback loop
├─ configs/                        # Comment-only phone, IMU, training, eval TOML
├─ docs/                           # Architecture, decisions, validation plan
├─ scripts/                        # Non-runnable future command placeholders
├─ tests/                          # Empty unit/integration/fixture structure
├─ gru_speed_model/                # Unpacked GRU checkpoint contents; incomplete
└─ SIH-2-main/.../IOVNBD-Speed-Prediction/
   └─ Teammate’s training/research project; keep as reference, don’t import wholesale
```

Focused review notes:

::code-comment{title="[P1] Synchronize model metadata" body="The runtime setting is a 5-second window, which evaluates to 50 timesteps, while its inline comment and the README still describe 20 timesteps / 2 seconds. Update the model manifest and documentation together; deployment must use the checkpoint's actual 50-sample contract." file="E:/dead reckoning/SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/config.py" start=101 end=102 priority=1}

::code-comment{title="[P2] Write artifacts once" body="Metrics, predictions, and combined results are written inside the loop that prints each metric, so the same files are needlessly overwritten four times and the log repeats its save message. Move the write block after the loop when this file is cleaned up." file="E:/dead reckoning/SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/evaluate.py" start=81 end=107 priority=2}

::code-comment{title="[P2] Validate pair alignment" body="The target is joined to phone samples by row position, but this function does not first assert equal S/V row counts or provide a meaningful alignment error. Validate the pair explicitly before constructing the dataframe, especially when future datasets are added." file="E:/dead reckoning/SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/preprocess.py" start=50 end=63 priority=2}

For the first learning pass, I recommend we start with the small `GRUSpeedRegressor` class in `train_model.py`: it is the exact model structure we will eventually wrap, and it is only about 20 lines. Say “start `train_model.py`” when you’re ready.

> what about doinf the deterministic, atleast the orientation and grav removal part first, then the velocity part since the model will be accepting cleaned inputs no in the actual pipeline

Yes—this is the better final architecture.

```text
Raw phone IMU
→ validation + timestamps
→ orientation estimation
→ phone-to-vehicle calibration
→ rotate accel/gyro into vehicle frame
→ remove gravity from accelerometer
→ cleaned 6-channel IMU window
→ GRU velocity prediction
→ uncertainty engine
→ EKF / NHC / GNSS / road context / map matching
```

The key correction: the teammate’s current GRU **cannot** receive cleaned inputs as-is. It was trained on raw, phone-axis accelerometer and gyroscope data, including gravity. Feeding it rotated, gravity-removed data changes the feature distribution completely.

So we should:

- Build the deterministic preprocessing first.
- Use that exact same preprocessing offline on IO-VNBD training data.
- Retrain the GRU on cleaned vehicle-frame inputs.
- Generate new feature and target scalers alongside the new checkpoint.

We can still reuse the GRU architecture—the input stays six channels—but not its current weights. The six clean features should be:

```text
linear_acc_vehicle_x/y/z     # gravity removed
gyro_vehicle_x/y/z           # rotated, but not gravity-removed
```

For the new model, I’d also train the target in **m/s**, rather than km/h, since the EKF operates naturally in SI units.

The learning/build order should be:

1. Define the IMU sample, units, timestamps, and coordinate-frame conventions.
2. Implement orientation estimation.
3. Implement dynamic phone-to-vehicle calibration.
4. Implement rotation and gravity removal.
5. Test those deterministic pieces with stationary, braking, turning, and phone-rotation cases.
6. Modify the velocity-training preprocessing so it produces these clean windows.
7. Retrain and package the GRU with its scalers.
8. Then build our uncertainty engine around that clean velocity observation.

One important long-term rule: we should not keep a separate orientation filter forever if the 15-state EKF also owns attitude. The early orientation component can provide initialization and preprocessing; later the EKF’s attitude state should become the authoritative orientation source.

For our first file-by-file lesson, I recommend starting with [`normalization.py`](</E:/dead reckoning/src/idr_backend/sensors/normalization.py>) rather than jumping straight into the filter. Orientation math is only understandable once the units and coordinate frames are fixed. Then we move directly to `orientation.py`, one function at a time.

> a few questions, isnt uncertainity engine the next step after velocity predictor, which is after calibrtion and preprocessing instead of parallel no,&#x20;
> and secondly, where have we defined the schema of the data we'll recieve from the sensors? shouldnt we do that before norm and preprocessing

You’re right on both points.

The uncertainty engine is **after** velocity prediction in the data flow:

```text
Cleaned IMU window
→ Velocity predictor
→ predicted speed
→ Uncertainty engine
→ speed + covariance / confidence
→ EKF measurement update
```

It is only “parallel” in the sense that both velocity and uncertainty use information from the same sensor window. But the uncertainty model should also receive the velocity prediction itself—plus quality signals such as IMU variance, turn rate, calibration confidence, and recent EKF innovation—so it is logically downstream of velocity.

And yes: we have **not defined the real sensor-data schema yet**. The scaffold deliberately left it as a TODO, so you correctly caught the first implementation step.

We should define the schema before normalization or preprocessing. In fact, there are three useful schema layers:

```text
1. RawSensorSample
   One accelerometer or gyroscope reading straight from Android/iOS/external IMU.

2. SynchronizedImuSample
   A validated accelerometer + gyroscope pair aligned to one timestamp,
   expressed in SI units and still in the phone/device frame.

3. VehicleImuSample
   The synchronized sample after orientation, phone-to-vehicle calibration,
   rotation, and gravity removal—ready for the velocity model and EKF.
```

The important distinction is that phones often emit accelerometer and gyroscope readings as separate callbacks. So we should not pretend they arrive as one perfectly aligned IMU sample; synchronization creates that combined sample.

The first actual file we should implement is therefore not `normalization.py` directly. It should be a new `sensors/types.py` (or `contracts/sensors.py`) defining these three data contracts, their timestamps, units, coordinate-frame labels, source metadata, and quality fields.

Then the order becomes:

```text
sensor schemas
→ ingestion
→ synchronization + normalization
→ orientation
→ phone-to-vehicle calibration
→ gravity removal
→ cleaned IMU window
→ velocity model
→ uncertainty model
→ EKF
```

That is the correct foundation.

> sure so lets start

<details><summary>2 previous messages</summary>

> We’ll start with the sensor contracts and keep this pass tightly scoped to the `sensors` package. First we’ll add only the coordinate-frame vocabulary—the foundation every later sample type and transform will rely on.
>
> <details><summary>Ran a command</summary>
>
> - Ran `Get-Content -Raw 'src\idr_backend\sensors\__init__.py'; Get-Content -Raw 'src\idr_backend\sensors\normalization.py'`
>
> </details>
</details>

We start with a new file: [`types.py`](</E:/dead reckoning/src/idr_backend/sensors/types.py>).

Before defining any sensor sample, we must define what a vector’s axes mean. Otherwise an acceleration value like `[1, 0, 0]` is meaningless: is it toward the phone’s right, the vehicle’s front, or east?

Add only this first block:

```python
"""Sensor data contracts and coordinate-frame conventions for IDR."""

from enum import StrEnum

class CoordinateFrame(StrEnum):
    """Supported coordinate frames for vector-valued sensor data."""

    SENSOR = "sensor"
    VEHICLE_FLU = "vehicle_flu"
    NAVIGATION_ENU = "navigation_enu"
```

What it means:

- `SENSOR`: raw axes reported by the phone or external IMU. Its exact physical orientation comes from source metadata and must not be assumed.
- `VEHICLE_FLU`: the cleaned vehicle frame: **F**orward, **L**eft, **U**p. This is what the velocity model and NHC will use.
- `NAVIGATION_ENU`: the world frame: **E**ast, **N**orth, **U**p. This is what GNSS and the EKF position state will use.

We deliberately do **not** include `"unknown"`. If the frame is unknown, ingestion must reject the observation rather than let bad data quietly reach the filter.

After you add that, tell me “done” and we’ll add the first actual sensor schema—one small type at a time.

> no this file doesnt exist, made and typed it in [types.py](src/idr_backend/sensors/types.py) , the rest of the file now,&#x20;
> fn, then expln, then fnand so on

<details><summary>2 previous messages</summary>

> Perfect—now that the file exists, I’ll read only `types.py` and continue it in the same rhythm: one definition, what it does, why it belongs in the schema, then the next definition.
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/sensors/types.py`
>
> </details>
</details>

Exactly. This file has no functions yet—it defines the nouns that every later function will process.

Keep your existing `CoordinateFrame`, add this import beneath `StrEnum`:

```python
from dataclasses import dataclass
```

Then append the following definitions, in this order.

### 1. Sensor kind

```python
class SensorKind(StrEnum):
    """Kinds of vector-valued inertial sensor readings used by IDR."""

    ACCELEROMETER = "accelerometer"
    GYROSCOPE = "gyroscope"
```

This tells us what the three numbers represent.

- An accelerometer measures linear acceleration plus gravity.
- A gyroscope measures angular velocity.
- We do not add a magnetometer here because it is not part of the trusted navigation pipeline.

### 2. Sensor source

```python
class SensorSource(StrEnum):
    """Physical source supplying an inertial sensor reading."""

    PHONE = "phone"
    EXTERNAL_IMU = "external_imu"
```

`SensorKind` says *what* was measured. `SensorSource` says *where it came from*.

A phone accelerometer and an external-IMU accelerometer are both `ACCELEROMETER`, but their noise, sampling rate, and mounting can be different.

### 3. Measurement units

```python
class MeasurementUnit(StrEnum):
    """Units accepted at the raw sensor boundary."""

    METERS_PER_SECOND_SQUARED = "m/s^2"
    RADIANS_PER_SECOND = "rad/s"
    STANDARD_GRAVITY = "g"
    DEGREES_PER_SECOND = "deg/s"
```

Incoming phone readings normally already use `m/s²` and `rad/s`. External IMUs may use `g` or degrees per second.

This is why the raw schema carries its unit: normalization must convert it rather than assume.

### 4. Small reusable aliases

```python
Vector3 = tuple[float, float, float]
QuaternionWxyz = tuple[float, float, float, float]
```

`Vector3` is simply an `(x, y, z)` tuple.

`QuaternionWxyz` represents orientation as `(w, x, y, z)`. We name the ordering explicitly because some libraries use `(x, y, z, w)` instead—a silent mix-up here ruins all later rotation math.

### 5. Raw sensor callback

```python
@dataclass(frozen=True, slots=True)
class RawSensorSample:
    """One unmodified vector reading received from a physical sensor."""

    timestamp_ns: int
    source: SensorSource
    source_id: str
    kind: SensorKind
    value: Vector3
    unit: MeasurementUnit
    frame: CoordinateFrame
    vendor_accuracy: int | None = None
```

This is the schema at the boundary of our system: one accelerometer or gyroscope callback.

Important fields:

- `timestamp_ns`: monotonic session time in nanoseconds—not wall-clock time. The filter needs reliable elapsed time.
- `source_id`: identifies the concrete device, for example `"phone-primary"` or `"fog-imu-01"`.
- `value`: the raw `(x, y, z)` measurement.
- `frame`: usually `SENSOR`; an externally mounted IMU could already declare `VEHICLE_FLU`.
- `vendor_accuracy`: optional raw platform metadata. We preserve it but do not trust its meaning until the adapter defines it.

`frozen=True` means samples cannot be accidentally mutated after creation. `slots=True` keeps a high-rate sensor stream lightweight.

### 6. Normalized individual reading

```python
@dataclass(frozen=True, slots=True)
class NormalizedSensorSample:
    """One validated sensor reading expressed in IDR's SI-unit convention."""

    timestamp_ns: int
    source: SensorSource
    source_id: str
    kind: SensorKind
    value: Vector3
    frame: CoordinateFrame
```

This is what comes out of normalization.

The unit field disappears because it is now guaranteed by `kind`:

- `ACCELEROMETER` values are always `m/s²`.
- `GYROSCOPE` values are always `rad/s`.

The coordinate frame may still be `SENSOR`; normalization fixes units and validity, not orientation.

### 7. Synchronized IMU sample

```python
@dataclass(frozen=True, slots=True)
class SynchronizedImuSample:
    """Aligned SI-unit accelerometer and gyroscope readings in one frame."""

    timestamp_ns: int
    source: SensorSource
    source_id: str
    frame: CoordinateFrame
    acceleration_mps2: Vector3
    angular_velocity_radps: Vector3
    accelerometer_timestamp_ns: int
    gyroscope_timestamp_ns: int
```

Phones emit accelerometer and gyro callbacks separately. The synchronizer creates this object only after choosing a pair close enough in time.

The three timestamps are intentional:

- `timestamp_ns`: the timestamp the rest of the pipeline uses.
- The other two timestamps: evidence of how far apart the original sensor readings were. Later, quality checks can reject pairs with excessive skew.

### 8. Orientation result

```python
@dataclass(frozen=True, slots=True)
class OrientationEstimate:
    """Estimated rotation from the sensor frame into navigation ENU."""

    timestamp_ns: int
    source: SensorSource
    source_id: str
    sensor_to_navigation_wxyz: QuaternionWxyz
```

This is produced by the orientation filter.

The name `sensor_to_navigation_wxyz` is deliberately long: it removes ambiguity. It means, “use this quaternion to rotate a vector in the sensor frame into East-North-Up navigation coordinates.”

### 9. Phone/IMU mounting calibration

```python
@dataclass(frozen=True, slots=True)
class VehicleCalibration:
    """Estimated rotation from the sensor frame into vehicle Forward-Left-Up."""

    timestamp_ns: int
    source: SensorSource
    source_id: str
    sensor_to_vehicle_wxyz: QuaternionWxyz
    confidence: float
```

Orientation answers: “Where is the sensor relative to the world?”

Calibration answers: “How is the sensor mounted relative to the vehicle?”

They are different rotations, so they need different schemas. `confidence` will later let us avoid trusting a calibration inferred from weak driving evidence.

### 10. Cleaned sample for the GRU and EKF

```python
@dataclass(frozen=True, slots=True)
class VehicleImuSample:
    """Calibrated, vehicle-frame IMU data ready for velocity prediction and fusion."""

    timestamp_ns: int
    source: SensorSource
    source_id: str
    linear_acceleration_mps2: Vector3
    angular_velocity_radps: Vector3
    vehicle_to_navigation_wxyz: QuaternionWxyz
    calibration_confidence: float
```

This is the output after rotation and gravity removal.

- `linear_acceleration_mps2`: vehicle-frame acceleration with gravity removed.
- `angular_velocity_radps`: gyro rotated into the vehicle frame.
- `vehicle_to_navigation_wxyz`: useful to the EKF; the GRU will mainly use the first two vectors.
- This is the exact clean representation on which we’ll later retrain the GRU.

Do not add validation methods yet. The next file, `normalization.py`, will implement the first functions: finite-number checks, timestamp checks, and unit conversion from `RawSensorSample` to `NormalizedSensorSample`.

Once you’ve typed this, say “done,” and we’ll start the first real function in `normalization.py`.

> done, just comment the file out more with the expln u gave in the chat here so that we know whats happening exactly later on
>
> and should it be norm first or orientation or calib, any lets do whichever u want, same format like we did on this one

<details><summary>4 previous messages</summary>

> I’ll add the explanatory comments directly to `types.py` so the rationale lives beside the schemas. After that we’ll begin with normalization: it is the first processing step, because orientation and calibration only make sense once every reading has known units, a valid timestamp, and a declared frame.
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/sensors/types.py`
>
> </details>
>
> I found two naming details worth fixing while the file is still isolated: `METRICS_PER...` should be `METERS_PER...`, and the orientation field should spell out `navigation` rather than abbreviate it. I’ll make those clarity-only corrections and add the explanation comments; no processing behavior is being introduced.
>
> <details><summary>Edited a file, ran a command</summary>
>
> - Wrote `./src/idr_backend/sensors/types.py` (+162 -68)
> - Ran `& 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m py_compile 'src\idr_backend\sensors\types.py'`
>
> </details>
</details>

I added the detailed explanation comments to [`types.py`](</E:/dead reckoning/src/idr_backend/sensors/types.py>) and verified it compiles.

The correct implementation order is:

```text
types/schema
→ normalization
→ synchronization
→ orientation
→ dynamic calibration
→ rotate into vehicle frame + gravity removal
→ cleaned IMU data for GRU and EKF
```

Normalization is next because it is pure and deterministic: it turns one raw callback into one valid SI-unit reading. It does not rotate anything, remove gravity, or combine the two sensors.

Open [`normalization.py`](</E:/dead reckoning/src/idr_backend/sensors/normalization.py>) and replace its current contents with this first function setup:

```python
"""Unit conversion and basic validation for raw inertial sensor readings."""

from math import isfinite, pi

from .types import (
    MeasurementUnit,
    NormalizedSensorSample,
    RawSensorSample,
    SensorKind,
)

STANDARD_GRAVITY_MPS2 = 9.80665

def normalize_raw_sample(sample: RawSensorSample) -> NormalizedSensorSample:
    """Validate one raw IMU reading and convert it into IDR's SI convention."""

    if sample.timestamp_ns < 0:
        raise ValueError("timestamp_ns must be non-negative")

    if not sample.source_id.strip():
        raise ValueError("source_id must not be empty")

    if not all(isfinite(component) for component in sample.value):
        raise ValueError("sensor values must all be finite")

    if sample.kind is SensorKind.ACCELEROMETER:
        if sample.unit is MeasurementUnit.METERS_PER_SECOND_SQUARED:
            scale = 1.0
        elif sample.unit is MeasurementUnit.STANDARD_GRAVITY:
            scale = STANDARD_GRAVITY_MPS2
        else:
            raise ValueError(
                f"accelerometer cannot use unit {sample.unit!r}"
            )

    elif sample.kind is SensorKind.GYROSCOPE:
        if sample.unit is MeasurementUnit.RADIANS_PER_SECOND:
            scale = 1.0
        elif sample.unit is MeasurementUnit.DEGREES_PER_SECOND:
            scale = pi / 180.0
        else:
            raise ValueError(
                f"gyroscope cannot use unit {sample.unit!r}"
            )

    else:
        raise ValueError(f"unsupported sensor kind {sample.kind!r}")

    x, y, z = sample.value

    return NormalizedSensorSample(
        timestamp_ns=sample.timestamp_ns,
        source=sample.source,
        source_id=sample.source_id,
        kind=sample.kind,
        value=(x * scale, y * scale, z * scale),
        frame=sample.frame,
    )
```

What this function does:

- Rejects an invalid timestamp, empty device ID, and `NaN`/infinite readings.
- Converts accelerometer values from `g` to `m/s²`.
- Converts gyroscope values from `deg/s` to `rad/s`.
- Preserves the source, sensor kind, timestamp, and coordinate frame.
- Returns a new immutable `NormalizedSensorSample`.

What it deliberately does **not** do:

- It does not combine accelerometer and gyro readings—that is synchronization.
- It does not rotate vectors—that requires orientation and calibration.
- It does not subtract gravity.
- It does not assume the raw frame is vehicle-aligned.

After you type this, say “done.” Then we’ll test this one function with a few sample inputs before moving to synchronization.

> next

<details><summary>2 previous messages</summary>

> I’ll check only the normalization function you just added, then we’ll write a small focused test for it. That test will prove unit conversion and invalid-input handling before we introduce time synchronization.
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/sensors/normalization.py`
>
> </details>
</details>

Almost there—don’t move on yet, because the final constructor has two important mistakes.

Replace only the `return NormalizedSensorSample(...)` block with:

```python
    return NormalizedSensorSample(
        timestamp_ns=sample.timestamp_ns,
        source=sample.source,
        source_id=sample.source_id,
        kind=sample.kind,
        value=(x * scale, y * scale, z * scale),
        frame=sample.frame,
    )
```

Why:

- Every argument inside a function call must end with a comma. Your `timestamp_ns` line is missing one.
- The dataclass field is named `kind`, so the keyword must be `kind=`.
- `SensorKind` is the enum class itself, not a field name.
- The spaces around `=` and `*` are only formatting, but they make Python easier to scan.

Optional cleanup afterward:

```python
STANDARD_GRAVITY_MPS2 = 9.80665
```

Constants are conventionally uppercase, so later code immediately signals that this is a fixed physical value.

Once that block is fixed, say “done” and we’ll write the first small test for this function.

> done

<details><summary>2 previous messages</summary>

> Great. I’ll verify only `normalization.py` now. If it compiles, we’ll add one focused normalization test—no synchronization or orientation code yet.
>
> <details><summary>Ran a command</summary>
>
> - Ran `& 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m py_compile 'src\idr_backend\sensors\types.py' 'src\idr_backend\sensors\normalization.py'`
>
> </details>
</details>

`types.py` and `normalization.py` compile successfully.

Now create [`test_normalization.py`](</E:/dead reckoning/tests/unit/test_normalization.py>) and add this one test function:

```python
from math import isclose

from idr_backend.sensors.normalization import normalize_raw_sample
from idr_backend.sensors.types import (
    CoordinateFrame,
    MeasurementUnit,
    RawSensorSample,
    SensorKind,
    SensorSource,
)

def test_normalize_accelerometer_from_standard_gravity() -> None:
    raw_sample = RawSensorSample(
        timestamp_ns=1_000_000,
        source=SensorSource.PHONE,
        source_id="phone-primary",
        kind=SensorKind.ACCELEROMETER,
        value=(0.0, 1.0, -1.0),
        unit=MeasurementUnit.STANDARD_GRAVITY,
        frame=CoordinateFrame.SENSOR,
    )

    normalized_sample = normalize_raw_sample(raw_sample)

    assert normalized_sample.timestamp_ns == raw_sample.timestamp_ns
    assert normalized_sample.kind is SensorKind.ACCELEROMETER
    assert normalized_sample.frame is CoordinateFrame.SENSOR

    expected_value = (0.0, 9.80665, -9.80665)
    for actual, expected in zip(normalized_sample.value, expected_value):
        assert isclose(actual, expected)
```

What this test proves:

- A raw accelerometer reading in `g` is accepted.
- `1 g` becomes `9.80665 m/s²`.
- The vector sign and component order stay unchanged.
- Timestamp, kind, and coordinate frame survive normalization.

We use `isclose()` rather than `==` for decimal floats, because floating-point arithmetic can produce tiny representation differences.

After you add it, say “done.” Then we’ll run this one test and add the next test: converting gyroscope degrees per second into radians per second.

> lets test it after a larger phase of completion like the whole deterministic part before velocity engine

<details><summary>3 previous messages</summary>

> That works. We’ll defer writing and running tests until the deterministic milestone is complete, then test the pipeline as a coherent unit. We’ll still keep each function small and explainable so testing can be added cleanly afterward.
>
> Normalization is complete, so the next dependency is synchronization: orientation needs one aligned accelerometer–gyroscope pair, not two unrelated callbacks.
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/sensors/synchronization.py`
>
> </details>
>
> Context compaction
>
> Source: automatic
> Status: completed
</details>

Yes—no tests until the deterministic sensor pipeline is complete.

Next is **timestamp synchronization**, because orientation needs matched accelerometer and gyroscope readings.

In [synchronization.py](E:/dead%20reckoning/src/idr_backend/sensors/synchronization.py), keep the module docstring and add these imports plus this one pure function:

```python
from .types import (
    NormalizedSensorSample,
    SensorKind,
    SynchronizedImuSample,
)

def synchronize_pair(
    accelerometer: NormalizedSensorSample,
    gyroscope: NormalizedSensorSample,
    max_skew_ns: int,
) -> SynchronizedImuSample:
    """Build one IMU reading from a compatible accelerometer/gyroscope pair."""

    if max_skew_ns < 0:
        raise ValueError("max_skew_ns must be zero or positive.")

    if accelerometer.kind is not SensorKind.ACCELEROMETER:
        raise ValueError("The first sample must be an accelerometer reading.")

    if gyroscope.kind is not SensorKind.GYROSCOPE:
        raise ValueError("The second sample must be a gyroscope reading.")

    if accelerometer.source != gyroscope.source:
        raise ValueError("Cannot synchronize samples from different sources.")

    if accelerometer.source_id != gyroscope.source_id:
        raise ValueError("Cannot synchronize samples from different devices.")

    if accelerometer.frame != gyroscope.frame:
        raise ValueError("Cannot synchronize samples expressed in different frames.")

    skew_ns = abs(accelerometer.timestamp_ns - gyroscope.timestamp_ns)
    if skew_ns > max_skew_ns:
        raise ValueError(
            f"Accelerometer and gyroscope timestamps differ by {skew_ns} ns, "
            f"which exceeds the allowed skew of {max_skew_ns} ns."
        )

    return SynchronizedImuSample(
        # Use the later timestamp: the combined reading is not available until
        # both physical measurements have arrived.
        timestamp_ns=max(accelerometer.timestamp_ns, gyroscope.timestamp_ns),
        source=accelerometer.source,
        source_id=accelerometer.source_id,
        frame=accelerometer.frame,
        acceleration_mps2=accelerometer.value,
        angular_velocity_radps=gyroscope.value,
        # Preserve originals so later diagnostics can expose actual skew.
        accelerometer_timestamp_ns=accelerometer.timestamp_ns,
        gyroscope_timestamp_ns=gyroscope.timestamp_ns,
    )
```

What it does:

- It accepts two already-normalized readings, so their units are guaranteed SI.
- It confirms the samples truly belong together: correct sensor kinds, same device, same source, and same coordinate frame.
- It rejects a pair that is too far apart in time. `max_skew_ns` stays explicit for now; later configuration will choose values per device.
- It preserves both original timestamps for diagnostics.
- It chooses the later timestamp as the combined sample’s time. This is causal: in a real stream, we cannot use the pair until both readings exist.

This deliberately does **not** buffer readings, search for nearest neighbours, interpolate, or resample. The next step will be a stateful synchronizer that does those streaming responsibilities, while this helper remains the strict “are these two samples a valid pair?” rule.

> done

<details><summary>2 previous messages</summary>

> Good—I'll check only the synchronization file you just completed, then we’ll add its next small piece without moving on to another subsystem.
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/sensors/synchronization.py`
>
> </details>
</details>

Your pairing logic is correct. I haven’t run tests, as agreed.

One small polish: make the top docstring describe the module, rather than repeating the function explanation. For example:

```python
"""Timestamp-alignment helpers for normalized IMU data."""
```

Now we add the stateful part: a synchronizer that will temporarily hold unmatched accelerometer/gyroscope samples. Add `deque`, `CoordinateFrame`, and `SensorSource` to the imports, then add this class below `synchronize_pair`:

```python
from collections import deque

# Add CoordinateFrame and SensorSource to your existing .types import.
```

```python
class ImuSynchronizer:
    """Hold pending normalized readings from one physical IMU stream."""

    def __init__(
        self,
        max_skew_ns: int,
        max_pending_samples: int = 32,
    ) -> None:
        """Create bounded buffers for temporarily unmatched IMU readings."""

        if max_skew_ns < 0:
            raise ValueError("max_skew_ns must be zero or positive.")

        if max_pending_samples <= 0:
            raise ValueError("max_pending_samples must be positive.")

        # This threshold is passed to synchronize_pair once a valid pair is found.
        self._max_skew_ns = max_skew_ns

        # A bound prevents unlimited memory growth if one sensor stops reporting.
        self._max_pending_samples = max_pending_samples

        # Acceleration and angular-velocity readings arrive independently.
        self._pending_accelerometer: deque[NormalizedSensorSample] = deque()
        self._pending_gyroscope: deque[NormalizedSensorSample] = deque()

        # One ImuSynchronizer instance must handle exactly one device and frame.
        # The first accepted sample establishes these values; push() will enforce
        # them for every later sample.
        self._source: SensorSource | None = None
        self._source_id: str | None = None
        self._frame: CoordinateFrame | None = None
```

What `__init__` does:

- Creates two small queues because accelerometer and gyroscope callbacks arrive separately.
- Stores the maximum allowed timestamp difference from the earlier function.
- Sets a memory limit for cases such as a gyroscope failure while accelerometer readings keep arriving.
- Leaves device identity unset initially. The next method, `push(sample)`, will lock the instance to the first device/frame it receives and reject accidental mixing of phone and external-IMU data.

Next we’ll write only `push()`: receive one normalized sample, place it in the appropriate queue, and return any valid synchronized pair.

> yes give push, and other snippets too, like one fn, then its detailed expln, then the other and its expln and so on for this file

Great. `push()` is the public method the pipeline will call once for every normalized sensor reading.

Add this inside `ImuSynchronizer`, below `__init__`:

```python
def push(
    self,
    sample: NormalizedSensorSample,
) -> tuple[SynchronizedImuSample, ...]:
    """Accept one normalized reading and return any newly matched IMU pairs."""

    if sample.kind not in (
        SensorKind.ACCELEROMETER,
        SensorKind.GYROSCOPE,
    ):
        raise ValueError(
            "ImuSynchronizer accepts only accelerometer or gyroscope readings."
        )

    # Lock this synchronizer to one physical device and coordinate frame.
    self._register_or_validate_stream(sample)

    # Store the reading in its acceleration or gyroscope queue.
    self._append_pending_sample(sample)

    # Match compatible queued readings and return the resulting IMU sample(s).
    return self._drain_pairs()
```

How it works:

1. `push()` receives exactly one `NormalizedSensorSample`—for example, one phone accelerometer callback.

2. It rejects unknown sensor kinds. Today we have only accelerometer and gyroscope, but this protects us if types such as magnetometer are added later.

3. `_register_or_validate_stream()` will establish the device identity from the first sample. After that, it prevents mistakes such as putting phone accelerometer data and external-IMU gyroscope data into the same synchronizer.

4. `_append_pending_sample()` will place the reading in the correct temporary queue, while enforcing timestamp and queue-size rules.

5. `_drain_pairs()` will locate compatible acceleration/gyro pairs, call your existing `synchronize_pair()`, and return the completed `SynchronizedImuSample` objects.

The return type is a tuple, even though the normal case returns either zero or one pair. That keeps the interface safe if future buffering releases multiple ready pairs in one call.

Type this first. Next we’ll add `_register_or_validate_stream()` and explain precisely why stream identity needs to be locked.

> yes give it

Add this next private method below `push()`:

```python
def _register_or_validate_stream(
    self,
    sample: NormalizedSensorSample,
) -> None:
    """Bind this synchronizer to its first device, then enforce that identity."""

    if self._source is None:
        # The first accepted sample defines the one stream this instance owns.
        self._source = sample.source
        self._source_id = sample.source_id
        self._frame = sample.frame
        return

    if (
        sample.source != self._source
        or sample.source_id != self._source_id
        or sample.frame != self._frame
    ):
        raise ValueError(
            "Cannot mix multiple sensor devices or coordinate frames in one "
            "ImuSynchronizer."
        )
```

What it does:

- On the first sample, it records the sensor source, physical device ID, and coordinate frame.
- On every later sample, it requires all three to match.
- This ensures one synchronizer represents one real IMU stream—for example, the phone IMU in its `sensor` frame.
- If we later use an external IMU too, the pipeline creates a separate `ImuSynchronizer` for it. We must never pair acceleration from one physical device with angular velocity from another.

The leading underscore means it is an internal implementation method. External pipeline code should only call `push()`.

Next will be `_append_pending_sample()`, where we decide the out-of-order timestamp and bounded-buffer policy.

> yes and other snippets too, like one fn, then its detailed expln, then the other and its expln and so on for this file in this pass only and the final flow and expln

Yes—let’s finish this file now. All methods below belong inside `ImuSynchronizer`, at the same indentation level as `push()`.

First, add these two fields at the end of `__init__`, after `_frame`:

```python
# This initial version requires readings from each sensor kind to arrive
# in increasing timestamp order. A future version may use a reorder window.
self._last_accelerometer_timestamp_ns: int | None = None
self._last_gyroscope_timestamp_ns: int | None = None
```

They let us identify duplicates and out-of-order callbacks.

### `_append_pending_sample`

```python
def _append_pending_sample(
    self,
    sample: NormalizedSensorSample,
) -> None:
    """Validate timestamp order and store a reading in its pending queue."""

    if sample.kind is SensorKind.ACCELEROMETER:
        pending_samples = self._pending_accelerometer
        previous_timestamp_ns = self._last_accelerometer_timestamp_ns
        sensor_name = "accelerometer"
    else:
        pending_samples = self._pending_gyroscope
        previous_timestamp_ns = self._last_gyroscope_timestamp_ns
        sensor_name = "gyroscope"

    if previous_timestamp_ns is not None:
        if sample.timestamp_ns == previous_timestamp_ns:
            raise ValueError(
                f"Duplicate {sensor_name} timestamp: {sample.timestamp_ns} ns."
            )

        if sample.timestamp_ns < previous_timestamp_ns:
            raise ValueError(
                f"Out-of-order {sensor_name} timestamp: "
                f"{sample.timestamp_ns} ns arrived after "
                f"{previous_timestamp_ns} ns."
            )

    if len(pending_samples) >= self._max_pending_samples:
        raise BufferError(
            f"Pending {sensor_name} buffer reached its limit of "
            f"{self._max_pending_samples} samples."
        )

    pending_samples.append(sample)

    if sample.kind is SensorKind.ACCELEROMETER:
        self._last_accelerometer_timestamp_ns = sample.timestamp_ns
    else:
        self._last_gyroscope_timestamp_ns = sample.timestamp_ns
```

Explanation:

- Chooses the correct queue based on whether this is acceleration or angular velocity.
- Enforces strictly increasing timestamps independently for each sensor type.
- Rejects duplicates rather than silently using the same physical reading twice.
- Rejects out-of-order data for this initial deterministic version. Later, if real devices require it, we can introduce a small reorder window deliberately.
- Rejects data once a queue is full. This is safer than allowing unlimited memory growth during a sensor gap.
- Updates the remembered timestamp only after the sample has safely entered its queue.

### `_drain_pairs`

```python
def _drain_pairs(self) -> tuple[SynchronizedImuSample, ...]:
    """Match queued readings in timestamp order and discard impossible matches."""

    synchronized_samples: list[SynchronizedImuSample] = []

    while self._pending_accelerometer and self._pending_gyroscope:
        accelerometer = self._pending_accelerometer[0]
        gyroscope = self._pending_gyroscope[0]

        timestamp_difference_ns = (
            accelerometer.timestamp_ns - gyroscope.timestamp_ns
        )

        if abs(timestamp_difference_ns) <= self._max_skew_ns:
            # The oldest readings are close enough in time, so they form one IMU
            # sample and can be removed from their respective queues.
            self._pending_accelerometer.popleft()
            self._pending_gyroscope.popleft()

            synchronized_samples.append(
                synchronize_pair(
                    accelerometer=accelerometer,
                    gyroscope=gyroscope,
                    max_skew_ns=self._max_skew_ns,
                )
            )
            continue

        if timestamp_difference_ns < 0:
            # Accelerometer is older than gyroscope and already too far behind.
            # Since accelerometer timestamps must increase, no future gyroscope
            # reading can make this particular accelerometer reading match.
            self._pending_accelerometer.popleft()
        else:
            # The gyroscope reading is the older impossible-to-match reading.
            self._pending_gyroscope.popleft()

        # TODO: Report discarded readings to the future sensor-quality component
        # so prolonged gaps and clock problems become observable diagnostics.

    return tuple(synchronized_samples)
```

Explanation:

- Looks only at the oldest queued accelerometer and gyro readings. Since each queue is timestamp ordered, this preserves chronological processing.
- If the two readings are within `max_skew_ns`, it removes both and creates a `SynchronizedImuSample` using your pure `synchronize_pair()` helper.
- If they are too far apart, it removes the older one. That reading can never match a future counterpart because future timestamps only increase.
- It may return no samples when it is still waiting for a compatible counterpart.
- It returns a tuple because one incoming reading can cause several buffered pairs to be released in future versions.

That completes the initial synchronization implementation. Its policy is intentionally strict:

- One synchronizer instance = one device + one frame.
- Per-sensor timestamps must be strictly increasing.
- Duplicate timestamps are rejected.
- Samples beyond the allowed accelerometer/gyro skew are discarded.
- A prolonged missing sensor eventually raises `BufferError` instead of consuming memory forever.

Current deterministic flow:

```text
RawSensorSample
    │
    ▼
normalize_raw_sample()
    │  validates values and converts to SI units
    ▼
NormalizedSensorSample
    │
    ▼
ImuSynchronizer.push()
    │
    ├── validates one device/frame and timestamp order
    ├── stores unmatched readings briefly
    └── pairs compatible acceleration + gyro readings
    │
    ▼
SynchronizedImuSample
    │
    ▼
orientation estimation   ← next file
```

Next we can begin `orientation.py`: first define exactly what orientation state means, then write its first small deterministic function.

> okay firstly, what all left in the deterministic pipeline, and yes orientation.py
>
> also, now check and evaluate the velocity models, teammates updated work [SIH-2-main](SIH-2-main/SIH-2-main/)  and [gru\_speed\_model](<gru_speed_model (1)/gru_speed_model/>) and [cnn\_speed\_model](cnn_speed_model/) , also, get his scripts in an ipynb so we can reuse the code when we change it or anything for the actual pipeline

<details><summary>18 previous messages</summary>

> I’ll first map the remaining deterministic stages, then inspect only the updated velocity-model code and artifacts. I’ll preserve the teammate projects and create a separate reusable notebook from the relevant scripts rather than copying their whole folders into our backend.
>
> <details><summary>Explored a file, ran 3 commands</summary>
>
> - Ran `rg --files src/idr_backend/sensors | Sort-Object`
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/sensors/orientation.py`
>
> </details>
>
> - Ran `rg --files 'SIH-2-main/SIH-2-main' 'gru_speed_model (1)/gru_speed_model' 'cnn_speed_model' | Sort-Object`
>
> - Ran `Get-Content -LiteralPath 'SIH-2-main/SIH-2-main/README.md' -ErrorAction SilentlyContinue`
>
> </details>
>
> The updated project still contains the GRU training code, while the GRU and CNN folders are checkpoint archives rather than source packages. I’m reading the training/evaluation scripts, reported metrics, and checkpoint metadata next; I’ll then turn the reusable script set into a separate notebook with provenance notes.
>
> <details><summary>Explored 7 files, ran 4 commands</summary>
>
> <details><summary>Explored 6 files</summary>
>
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/preprocess.py`
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/config.py`
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/train_model.py`
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/run_pipeline.py`
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/create_sequences.py`
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/train_baseline.py`
>
> </details>
>
> - Ran `Get-Item -LiteralPath 'gru_speed_model (1)/gru_speed_model','cnn_speed_model/cnn_speed_model' | Select-Object FullName,Length,LastWriteTime | Format-List`
>
> <details><summary>Explored a file</summary>
>
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/evaluate.py`
>
> </details>
>
> - Ran `Get-Content -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/results/gru_test_metrics.json'; Get-Content -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/results/final_results.json'; Get-Content -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/results/baseline_metrics.json'; Get-Content -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/run_log.txt'`
>
> - Ran `Get-Content -AsByteStream -ReadCount 0 -LiteralPath 'gru_speed_model (1)/gru_speed_model/data.pkl' | & 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "import sys,pickletools; pickletools.dis(sys.stdin.buffer.read())"`
>
> - Ran `Get-Content -AsByteStream -ReadCount 0 -LiteralPath 'cnn_speed_model/cnn_speed_model/data.pkl' | & 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "import sys,pickletools; pickletools.dis(sys.stdin.buffer.read())"`
>
> </details>
>
> One important early finding: the updated GRU has a credible held-out-sequence evaluation, but its saved model/scalers are not in the teammate project—only separately unpacked checkpoints are present. I’m checking whether those checkpoints contain enough metadata to be safely reusable and comparing the CNN architecture before deciding what belongs in the notebook.
>
> <details><summary>Explored 4 files, ran 6 commands</summary>
>
> - Ran `Get-Content -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/create_sequences.py' | Select-Object -Skip 90`
>
> <details><summary>Explored 3 files</summary>
>
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/train_model.py`
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/run_pipeline.py`
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/evaluate.py`
>
> </details>
>
> - Ran `Get-Content -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/results/gru_test_metrics.json'; Get-Content -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/results/final_results.json'; Get-Content -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/results/baseline_metrics.json'; Get-Content -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/results/training_history.json'`
>
> - Ran `& 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "from pathlib import Path; import pickletools; paths=[Path(r'gru_speed_model (1)/gru_speed_model/data.pkl'),Path(r'cnn_speed_model/cnn_speed_model/data.pkl')]; [print('\nPATH:',p,'\nSIZE:',p.stat().st_size,'\nHEAD:',p.read_bytes()[:32]) for p in paths]"`
>
> - Ran `Get-Content -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/README.md'; Get-Content -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/requirements.txt'`
>
> - Ran `& 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "from pathlib import Path; import pickletools; p=Path(r'gru_speed_model (1)/gru_speed_model/data.pkl'); pickletools.dis(p.read_bytes())"`
>
> - Ran `& 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "from pathlib import Path; import pickletools; p=Path(r'cnn_speed_model/cnn_speed_model/data.pkl'); pickletools.dis(p.read_bytes())"`
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/sensors/synchronization.py`
>
> </details>
>
> </details>
>
> The CNN checkpoint is structurally different: it advertises 7 inputs and a 3-block 1D-CNN, whereas the GRU is a 6-input model. I’m verifying both checkpoints with PyTorch’s restricted weights-only loader and reading the persisted metrics separately, so we distinguish confirmed facts from inference.
>
> <details><summary>Explored 4 files, ran 3 commands</summary>
>
> <details><summary>Explored 3 files</summary>
>
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/results/gru_test_metrics.json`
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/results/final_results.json`
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/results/baseline_metrics.json`
>
> </details>
>
> - Ran `Get-Content -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/results/training_history.json' | Select-Object -First 60`
>
> - Ran `& 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c @'
>
> from io import BytesIO
> from pathlib import Path
> from zipfile import ZIP_DEFLATED, ZipFile
> import torch
>
> for directory in (
>     Path(r"gru_speed_model (1)/gru_speed_model"),
>     Path(r"cnn_speed_model/cnn_speed_model"),
> ):
>     archive = BytesIO()
>     with ZipFile(archive, "w", compression=ZIP_DEFLATED) as zf:
>         for member in directory.rglob("*"):
>             if member.is_file():
>                 zf.write(member, member.relative_to(directory.parent).as_posix())
>
>     archive.seek(0)
>     checkpoint = torch.load(archive, map_location="cpu", weights_only=True)
>     print(f"\n{directory.parent.name}")
>     print("metadata:", {key: value for key, value in checkpoint.items() if key != "model_state_dict"})
>     print("state shapes:")
>     for key, tensor in checkpoint["model_state_dict"].items():
>         print(f"  {key}: {tuple(tensor.shape)}")
>
> '@`
>
> <details><summary>Explored a file</summary>
>
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/run_pipeline.py`
>
> </details>
>
> - Ran `Get-Content -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/inspect_data.py' | Select-Object -First 260`
>
> </details>
>
> The bundled Python has no PyTorch, so it cannot load either checkpoint here; that is an environment limitation, not a model failure. I’m checking the locally installed Python runtimes next. I also spotted four small synchronization corrections we should make before orientation—one would prevent `ImuSynchronizer` from being constructed.
>
> <details><summary>Ran 4 commands</summary>
>
> - Ran `Get-Command python -All | Select-Object Source,Version | Format-Table -AutoSize; py -0p`
> - Ran `Get-ChildItem -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction' -Force | Select-Object Name,Mode; Get-ChildItem -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction' -Directory -Force -Recurse -Depth 2 | Where-Object { $_.Name -match 'venv|env' } | Select-Object FullName`
> - Ran `Get-Content -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/evaluate.py' | Select-Object -Skip 50 -First 230`
> - Ran `Get-Content -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/config.py' | Select-Object -Skip 70 -First 90`
>
> </details>
>
> The runtime check is still running; I’ll wait briefly for its result, then create the notebook and give you the deterministic-stage map plus the model verdict.
>
> <details><summary>Ran a command</summary>
>
> - Ran `python -c "import sys; print(sys.executable); import torch; print(torch.__version__)"`
>
> </details>
>
> I’m creating a separate source-workbench notebook now. It will contain editable snapshots of the six reusable teammate scripts (configuration, inspection, preprocessing, windowing, GRU training, evaluation), while excluding raw data, results, baseline code, and checkpoints. Its opening notes will flag the required retraining changes for our cleaned vehicle-frame inputs.
>
> <details><summary>Ran 6 commands</summary>
>
> - Ran `$file = Resolve-Path -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/config.py'; [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($file))`
> - Ran `$file = Resolve-Path -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/inspect_data.py'; [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($file))`
> - Ran `$file = Resolve-Path -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/preprocess.py'; [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($file))`
> - Ran `$file = Resolve-Path -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/create_sequences.py'; [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($file))`
> - Ran `$file = Resolve-Path -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/train_model.py'; [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($file))`
> - Ran `$file = Resolve-Path -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/evaluate.py'; [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($file))`
>
> </details>
>
> The notebook content is ready; the first creation attempt only hit a JavaScript decoding limitation in the tool layer, and no files were changed. I’ll rerun the same creation with a local decoder.
>
> <details><summary>Created a file, ran 12 commands</summary>
>
> - Ran `$file = Resolve-Path -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/inspect_data.py'; [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($file))`
> - Ran `$file = Resolve-Path -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/preprocess.py'; [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($file))`
> - Ran `$file = Resolve-Path -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/train_model.py'; [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($file))`
> - Ran `$file = Resolve-Path -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/create_sequences.py'; [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($file))`
> - Ran `$file = Resolve-Path -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/config.py'; [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($file))`
> - Ran `$file = Resolve-Path -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/evaluate.py'; [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($file))`
> - Ran `$file = Resolve-Path -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/config.py'; [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($file))`
> - Ran `$file = Resolve-Path -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/preprocess.py'; [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($file))`
> - Ran `$file = Resolve-Path -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/create_sequences.py'; [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($file))`
> - Ran `$file = Resolve-Path -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/train_model.py'; [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($file))`
> - Ran `$file = Resolve-Path -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/evaluate.py'; [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($file))`
> - Ran `$file = Resolve-Path -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/inspect_data.py'; [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($file))`
> - Wrote `./notebooks/velocity_model_source_workbench.ipynb` (+151 -0)
>
> </details>
>
> The notebook has been created with six editable source snapshots and explicit integration warnings. I’m validating its JSON now, then I’ll give you: the remaining deterministic checklist, a concise GRU/CNN verdict, the four synchronization fixes, and the first orientation building block.
>
> <details><summary>Explored a file, ran 3 commands</summary>
>
> - Ran `$notebook = Get-Content -LiteralPath 'notebooks/velocity_model_source_workbench.ipynb' -Raw | ConvertFrom-Json; [PSCustomObject]@{ NbFormat = $notebook.nbformat; Cells = $notebook.cells.Count; SnapshotCells = @($notebook.cells | Where-Object { $_.metadata.tags -contains 'source-snapshot' }).Count; Kernelspec = $notebook.metadata.kernelspec.display_name } | Format-List`
>
> - Ran `Get-Item -LiteralPath 'notebooks/velocity_model_source_workbench.ipynb' | Select-Object FullName,Length,LastWriteTime | Format-List`
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/sensors/types.py`
>
> </details>
>
> - Ran `Get-Content -LiteralPath 'src/idr_backend/sensors/calibration.py'; Get-Content -LiteralPath 'src/idr_backend/sensors/gravity_removal.py'; Get-Content -LiteralPath 'src/idr_backend/sensors/quality.py'; Get-Content -LiteralPath 'src/idr_backend/sensors/ingestion.py'`
>
> </details>
</details>

I created and validated [velocity_model_source_workbench.ipynb](</E:/dead reckoning/notebooks/velocity_model_source_workbench.ipynb>). It has six editable source snapshots—config, inspection, preprocessing, windowing, GRU training, and evaluation—without copying datasets, checkpoints, results, or baseline code.

## Deterministic work remaining before velocity

| Stage | Status | Required output |
|---|---|---|
| Sensor contracts | Done | `RawSensorSample` through `VehicleImuSample` |
| Unit normalization | Done | SI-unit `NormalizedSensorSample` |
| Accel/gyro synchronization | Implemented, needs four fixes below | `SynchronizedImuSample` |
| Fixed-rate resampling + causal model window | Not started | Clean, evenly sampled IMU window |
| Orientation | Starting now | Sensor → navigation quaternion |
| Phone-to-vehicle calibration | Not started | Sensor → FLU quaternion + confidence |
| Rotate vectors into vehicle frame | Not started | FLU acceleration and gyro |
| Gravity removal | Not started | Vehicle-frame linear acceleration |
| Sensor quality / gaps / remount detection | Not started | Quality flags for model and EKF |
| Pre-velocity configuration/provenance | Not started | Feature order, units, rate, window length |

The velocity model must receive the final clean six channels:

```text
linear acceleration in vehicle FLU: x, y, z
angular velocity in vehicle FLU:    x, y, z
```

## Velocity-model evaluation

The GRU is reusable as a training-code starting point, but its current checkpoint is not deployable in our pipeline.

- Dataset: 40 journeys, 692,721 rows, about 19.4 hours, sampled at 10 Hz.
- Input: six raw phone-frame channels, including gravity.
- Target: indicated vehicle speed in km/h.
- Window: 50 samples = 5 seconds; stride 5 samples.
- Architecture: 2-layer GRU, hidden size 64, dropout 0.2, then `64 → 32 → 1`.
- Held-out journey result: MAE **17.24 km/h**, RMSE **23.02 km/h**, R² **0.267**.
- It is only modestly better than the Random Forest baseline: MAE 17.94 km/h, RMSE 24.80 km/h, R² 0.149.

So: use the GRU architecture and training structure, but retrain from scratch after our deterministic preprocessing is ready. Train the new target in **m/s**, not km/h, for EKF compatibility.

The CNN cannot yet be evaluated fairly:

- Checkpoint metadata indicates 7 inputs, 50 samples, channels `(32, 64, 64)`, kernel size 3, dropout 0.3.
- There is no matching CNN source, feature manifest, scaler, target scaler, or reported metrics.
- Both standalone GRU/CNN checkpoints lack the fitted scalers required to convert model values to physical speed.

Important teammate-code fixes for later:

- Comments say 20 samples / 2 seconds, but actual configuration is 50 samples / 5 seconds.
- `evaluate.py` saves metrics and predictions four times because artifact-writing is indented inside the metric-print loop.
- `preprocess.py` assumes S/V row counts match but should explicitly reject mismatches.
- Future loading should use `weights_only=True` for a known state-dict checkpoint.
- The current project contains result files but not its original `models/` or `artifacts/` directories.

I did not run model inference: the workspace’s bundled Python lacks PyTorch, and inference would still be invalid without the missing scalers.

## Fix synchronization before orientation

Make these static corrections in `synchronization.py`:

```python
self._pending_accelerometer: deque[NormalizedSensorSample] = deque()
self._pending_gyroscope: deque[NormalizedSensorSample] = deque()

self._last_accelerometer_timestamp_ns: int | None = None
self._last_gyroscope_timestamp_ns: int | None = None
```

```python
# In _register_or_validate_stream:
sample.source_id != self._source_id
```

```python
# In push:
) -> tuple[SynchronizedImuSample, ...]:
```

And move this line outside the `while` loop in `_drain_pairs()`:

```python
return tuple(synchronized_samples)
```

Otherwise the synchronizer returns after discarding only one unmatched sample.

## Orientation: first function

In `orientation.py`, replace the current module docstring with:

```python
"""Quaternion helpers and IMU-only orientation estimation.

Quaternion convention:
- quaternions use (w, x, y, z) ordering;
- sensor_to_navigation maps a sensor-frame vector into navigation ENU:
  v_navigation = q * (0, v_sensor) * conjugate(q);
- orientation is distinct from phone-to-vehicle mounting calibration.
"""
```

Then add:

```python
from math import isfinite, sqrt

from .types import QuaternionWxyz

def normalize_quaternion(
    quaternion: QuaternionWxyz,
) -> QuaternionWxyz:
    """Return a unit quaternion in the project's (w, x, y, z) convention."""

    w, x, y, z = quaternion

    if not all(isfinite(component) for component in quaternion):
        raise ValueError("Quaternion components must all be finite.")

    norm_squared = w * w + x * x + y * y + z * z
    if norm_squared <= 1e-24:
        raise ValueError("Cannot normalize a zero or near-zero quaternion.")

    norm = sqrt(norm_squared)
    return (w / norm, x / norm, y / norm, z / norm)
```

A quaternion represents a rotation only when its length is one. Gyroscope propagation slowly changes numerical length, so every later orientation update will pass through this function. It does not estimate attitude itself; it establishes the non-negotiable mathematical invariant needed by quaternion multiplication, vector rotation, and the eventual Mahony-style filter.

No deterministic tests were run, as requested.

> wait whats the rolw of a quaternion if we alr had the coordframe and 3 valued vectors for both the sensors&#x20;
>
> and next yes

`CoordinateFrame` tells us the **name of the axes** used by a vector. A quaternion tells us **how those axes are currently rotated relative to another frame**.

For example:

```text
acceleration = (0.0, 9.81, 0.0)
frame        = SENSOR
```

This only says “the phone measured 9.81 along its own y-axis.” It does not tell us where the phone’s y-axis points in the vehicle or in the world.

At the next moment, the driver may rotate the phone. The frame is still `SENSOR`, but its orientation has changed. The time-varying quaternion provides that missing relationship:

```text
q_sensor_to_navigation(t)
```

It lets us transform values:

```text
sensor-frame vector
        │
        │ quaternion rotation
        ▼
navigation ENU vector
```

A quaternion has four stored numbers, but only three independent degrees of freedom because its length is always one. It avoids Euler-angle gimbal lock and makes repeated 3D rotations stable.

We will eventually have two different quaternions:

```text
q_sensor_to_navigation(t)   dynamic: phone orientation in the world
q_sensor_to_vehicle         mostly fixed: how the phone is mounted in the car
```

The coordinate-frame enum names the endpoints; the quaternion performs the actual rotation between them.

Assuming you have added `normalize_quaternion()`, add this next function in `orientation.py`:

```python
def quaternion_multiply(
    left: QuaternionWxyz,
    right: QuaternionWxyz,
) -> QuaternionWxyz:
    """Return left ⊗ right, applying right before left."""

    if not all(isfinite(component) for component in (*left, *right)):
        raise ValueError("Quaternion components must all be finite.")

    left_w, left_x, left_y, left_z = left
    right_w, right_x, right_y, right_z = right

    return (
        left_w * right_w - left_x * right_x - left_y * right_y - left_z * right_z,
        left_w * right_x + left_x * right_w + left_y * right_z - left_z * right_y,
        left_w * right_y - left_x * right_z + left_y * right_w + left_z * right_x,
        left_w * right_z + left_x * right_y - left_y * right_x + left_z * right_w,
    )
```

This combines rotations. Its order matters: 3D rotations are not commutative.

For example, the eventual vehicle-to-navigation rotation is:

```text
q_vehicle_to_navigation
    = q_sensor_to_navigation ⊗ inverse(q_sensor_to_vehicle)
```

We deliberately do not normalize inside `quaternion_multiply()`. Later, the same multiplication will rotate vectors using `q ⊗ (0, vector) ⊗ conjugate(q)`; normalizing that intermediate vector quaternion would incorrectly change the vector’s magnitude.

> done that, yes and other snippets too, like one fn, then its detailed expln, then the other and its expln and so on for this file in this pass only and the final flow and expln

<details><summary>2 previous messages</summary>

> I’ll inspect only `orientation.py` now, then finish its initial quaternion/orientation layer in one pass: one method at a time with its purpose, followed by the complete data flow.
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/sensors/orientation.py`
>
> </details>
</details>

Your two existing functions are logically correct. Keep them, then finish `orientation.py` as follows. This is an IMU-only complementary attitude estimator: gyroscope propagation plus accelerometer correction when acceleration is plausibly dominated by gravity.

First, replace the `.types` import and add the constant:

```python
from .types import (
    CoordinateFrame,
    OrientationEstimate,
    QuaternionWxyz,
    SensorSource,
    SynchronizedImuSample,
    Vector3,
)

_NAVIGATION_UP: Vector3 = (0.0, 0.0, 1.0)
```

`_NAVIGATION_UP` is used because a resting accelerometer measures specific force pointing upward, approximately `+9.80665 m/s²`.

### `quaternion_conjugate`

```python
def quaternion_conjugate(
    quaternion: QuaternionWxyz,
) -> QuaternionWxyz:
    """Return the conjugate of a quaternion."""

    if not all(isfinite(component) for component in quaternion):
        raise ValueError("Quaternion components must all be finite.")

    w, x, y, z = quaternion
    return (w, -x, -y, -z)
```

For a unit quaternion, its conjugate is also its inverse rotation. We need it for:

```text
q ⊗ (0, vector) ⊗ conjugate(q)
```

which rotates a vector without changing its length.

### `vector_magnitude`

```python
def vector_magnitude(vector: Vector3) -> float:
    """Return the Euclidean length of a finite three-dimensional vector."""

    if not all(isfinite(component) for component in vector):
        raise ValueError("Vector components must all be finite.")

    x, y, z = vector
    return sqrt(x * x + y * y + z * z)
```

This measures a vector’s physical size. We use it to check whether acceleration is near gravity and to turn an angular-rotation vector into a quaternion.

### `normalize_vector`

```python
def normalize_vector(vector: Vector3) -> Vector3:
    """Return a unit vector with the same direction as the input vector."""

    magnitude = vector_magnitude(vector)
    if magnitude <= 1e-12:
        raise ValueError("Cannot normalize a zero or near-zero vector.")

    x, y, z = vector
    return (x / magnitude, y / magnitude, z / magnitude)
```

A direction should not depend on the sensor magnitude. For example, a resting accelerometer may measure 9.7 or 9.9 m/s², but both indicate the same approximate gravity direction.

### `quaternion_from_vector_alignment`

```python
def quaternion_from_vector_alignment(
    from_vector: Vector3,
    to_vector: Vector3,
) -> QuaternionWxyz:
    """Return the shortest rotation that maps from_vector onto to_vector."""

    from_x, from_y, from_z = normalize_vector(from_vector)
    to_x, to_y, to_z = normalize_vector(to_vector)

    dot_product = (
        from_x * to_x
        + from_y * to_y
        + from_z * to_z
    )
    dot_product = max(-1.0, min(1.0, dot_product))

    if dot_product >= 1.0 - 1e-12:
        return (1.0, 0.0, 0.0, 0.0)

    if dot_product <= -1.0 + 1e-12:
        # For opposite vectors, choose any stable axis perpendicular to
        # from_vector, then rotate 180 degrees about that axis.
        if abs(from_x) <= abs(from_y) and abs(from_x) <= abs(from_z):
            reference = (1.0, 0.0, 0.0)
        elif abs(from_y) <= abs(from_z):
            reference = (0.0, 1.0, 0.0)
        else:
            reference = (0.0, 0.0, 1.0)

        reference_x, reference_y, reference_z = reference
        axis = normalize_vector(
            (
                from_y * reference_z - from_z * reference_y,
                from_z * reference_x - from_x * reference_z,
                from_x * reference_y - from_y * reference_x,
            )
        )
        return (0.0, axis[0], axis[1], axis[2])

    cross_x = from_y * to_z - from_z * to_y
    cross_y = from_z * to_x - from_x * to_z
    cross_z = from_x * to_y - from_y * to_x

    return normalize_quaternion(
        (1.0 + dot_product, cross_x, cross_y, cross_z)
    )
```

This creates a rotation from two directions. We use it to align the measured “up” direction from the accelerometer with navigation up.

It handles three cases:

- Same direction → identity rotation.
- Opposite directions → a 180° rotation around a perpendicular axis.
- Everything else → shortest valid 3D rotation.

### `quaternion_from_rotation_vector`

Add `cos` and `sin` to your math import:

```python
from math import cos, isfinite, sin, sqrt
```

Then add:

```python
def quaternion_from_rotation_vector(
    rotation_vector_rad: Vector3,
) -> QuaternionWxyz:
    """Convert an axis-angle rotation vector in radians into a quaternion."""

    angle_rad = vector_magnitude(rotation_vector_rad)
    if angle_rad <= 1e-12:
        return (1.0, 0.0, 0.0, 0.0)

    half_angle_rad = angle_rad / 2.0
    scale = sin(half_angle_rad) / angle_rad

    rotation_x, rotation_y, rotation_z = rotation_vector_rad
    return normalize_quaternion(
        (
            cos(half_angle_rad),
            rotation_x * scale,
            rotation_y * scale,
            rotation_z * scale,
        )
    )
```

A gyroscope reports angular velocity in rad/s. Multiplying it by elapsed time gives an axis-angle rotation vector in radians. This function turns that small physical rotation into a quaternion.

### `rotate_vector`

```python
def rotate_vector(
    quaternion: QuaternionWxyz,
    vector: Vector3,
) -> Vector3:
    """Rotate a vector by a sensor-to-navigation quaternion."""

    unit_quaternion = normalize_quaternion(quaternion)
    vector_quaternion: QuaternionWxyz = (0.0, vector[0], vector[1], vector[2])

    rotated = quaternion_multiply(
        quaternion_multiply(unit_quaternion, vector_quaternion),
        quaternion_conjugate(unit_quaternion),
    )

    return (rotated[1], rotated[2], rotated[3])
```

This is where the quaternion actually transforms a three-value sensor reading between coordinate frames.

For example, it converts phone-frame acceleration into navigation-frame acceleration:

```text
accelerometer in SENSOR frame
            │
            ▼
rotate_vector(sensor_to_navigation, acceleration)
            │
            ▼
acceleration in navigation frame
```

### `propagate_orientation`

```python
def propagate_orientation(
    orientation_wxyz: QuaternionWxyz,
    angular_velocity_radps: Vector3,
    delta_time_s: float,
) -> QuaternionWxyz:
    """Propagate sensor-to-navigation orientation using gyroscope motion."""

    if not isfinite(delta_time_s) or delta_time_s <= 0.0:
        raise ValueError("delta_time_s must be finite and positive.")

    angular_x, angular_y, angular_z = angular_velocity_radps
    rotation_vector_rad = (
        angular_x * delta_time_s,
        angular_y * delta_time_s,
        angular_z * delta_time_s,
    )

    delta_rotation = quaternion_from_rotation_vector(rotation_vector_rad)

    # The gyro is expressed in sensor axes, so its incremental rotation is
    # applied on the right of the current sensor-to-navigation orientation.
    return normalize_quaternion(
        quaternion_multiply(orientation_wxyz, delta_rotation)
    )
```

This is pure gyroscope integration. It is excellent over short periods but gradually drifts because gyroscopes have bias. The upcoming estimator class corrects roll and pitch using trustworthy accelerometer readings.

### `is_acceleration_trustworthy`

```python
def is_acceleration_trustworthy(
    acceleration_mps2: Vector3,
    expected_gravity_mps2: float,
    tolerance_mps2: float,
) -> bool:
    """Return whether acceleration magnitude is close enough to gravity."""

    if not isfinite(expected_gravity_mps2) or expected_gravity_mps2 <= 0.0:
        raise ValueError("expected_gravity_mps2 must be finite and positive.")

    if not isfinite(tolerance_mps2) or tolerance_mps2 < 0.0:
        raise ValueError("tolerance_mps2 must be finite and non-negative.")

    return (
        abs(vector_magnitude(acceleration_mps2) - expected_gravity_mps2)
        <= tolerance_mps2
    )
```

Acceleration is only useful as a gravity-direction correction when the car is not accelerating or braking hard. During a turn or acceleration, treating the total acceleration as gravity would tilt the orientation incorrectly.

### `ImuOrientationEstimator.__init__`

```python
class ImuOrientationEstimator:
    """Estimate tilt with gyroscope propagation and gated accelerometer correction."""

    def __init__(
        self,
        *,
        accelerometer_correction_gain_per_s: float,
        acceleration_trust_tolerance_mps2: float,
        expected_gravity_mps2: float = 9.80665,
        initial_orientation_wxyz: QuaternionWxyz = (1.0, 0.0, 0.0, 0.0),
    ) -> None:
        """Create an estimator for one physical IMU stream."""

        if (
            not isfinite(accelerometer_correction_gain_per_s)
            or accelerometer_correction_gain_per_s < 0.0
        ):
            raise ValueError(
                "accelerometer_correction_gain_per_s must be finite and non-negative."
            )

        if (
            not isfinite(acceleration_trust_tolerance_mps2)
            or acceleration_trust_tolerance_mps2 < 0.0
        ):
            raise ValueError(
                "acceleration_trust_tolerance_mps2 must be finite and non-negative."
            )

        if not isfinite(expected_gravity_mps2) or expected_gravity_mps2 <= 0.0:
            raise ValueError("expected_gravity_mps2 must be finite and positive.")

        self._accelerometer_correction_gain_per_s = (
            accelerometer_correction_gain_per_s
        )
        self._acceleration_trust_tolerance_mps2 = (
            acceleration_trust_tolerance_mps2
        )
        self._expected_gravity_mps2 = expected_gravity_mps2

        self._initial_orientation_wxyz = normalize_quaternion(
            initial_orientation_wxyz
        )
        self._orientation_wxyz = self._initial_orientation_wxyz
        self._last_timestamp_ns: int | None = None

        self._source: SensorSource | None = None
        self._source_id: str | None = None
```

This stores state for one device. The gain and tolerance are deliberately supplied by configuration later; we should not hard-code tuning decisions in the filter.

`initial_orientation_wxyz` can later contain GNSS/EKF-seeded heading. Without that seed, IMU-only orientation can level roll/pitch but cannot determine true ENU yaw.

### `ImuOrientationEstimator._register_or_validate_stream`

```python
    def _register_or_validate_stream(
        self,
        sample: SynchronizedImuSample,
    ) -> None:
        """Bind the estimator to its first IMU source and device identifier."""

        if self._source is None:
            self._source = sample.source
            self._source_id = sample.source_id
            return

        if (
            sample.source != self._source
            or sample.source_id != self._source_id
        ):
            raise ValueError(
                "Cannot mix multiple physical IMU streams in one "
                "ImuOrientationEstimator."
            )
```

Like synchronization, one estimator owns exactly one physical IMU. A phone and external IMU need separate orientation states.

### `ImuOrientationEstimator.update`

```python
    def update(
        self,
        sample: SynchronizedImuSample,
    ) -> OrientationEstimate:
        """Update orientation from one synchronized IMU sample."""

        if sample.frame is not CoordinateFrame.SENSOR:
            raise ValueError(
                "ImuOrientationEstimator expects synchronized SENSOR-frame data."
            )

        self._register_or_validate_stream(sample)

        if (
            self._last_timestamp_ns is not None
            and sample.timestamp_ns <= self._last_timestamp_ns
        ):
            raise ValueError(
                "Orientation timestamps must be strictly increasing."
            )

        acceleration_is_trusted = is_acceleration_trustworthy(
            sample.acceleration_mps2,
            self._expected_gravity_mps2,
            self._acceleration_trust_tolerance_mps2,
        )

        if self._last_timestamp_ns is None:
            # On the first trustworthy sample, correct initial roll/pitch by
            # mapping measured specific force toward navigation up. Yaw remains
            # whatever was supplied by initial_orientation_wxyz.
            if acceleration_is_trusted:
                measured_up_navigation = rotate_vector(
                    self._orientation_wxyz,
                    normalize_vector(sample.acceleration_mps2),
                )
                tilt_correction = quaternion_from_vector_alignment(
                    measured_up_navigation,
                    _NAVIGATION_UP,
                )
                self._orientation_wxyz = normalize_quaternion(
                    quaternion_multiply(
                        tilt_correction,
                        self._orientation_wxyz,
                    )
                )

            self._last_timestamp_ns = sample.timestamp_ns
            return OrientationEstimate(
                timestamp_ns=sample.timestamp_ns,
                source=sample.source,
                source_id=sample.source_id,
                sensor_to_navigation_wxyz=self._orientation_wxyz,
            )

        delta_time_s = (
            sample.timestamp_ns - self._last_timestamp_ns
        ) * 1e-9

        updated_orientation = propagate_orientation(
            self._orientation_wxyz,
            sample.angular_velocity_radps,
            delta_time_s,
        )

        if acceleration_is_trusted:
            measured_up_navigation = rotate_vector(
                updated_orientation,
                normalize_vector(sample.acceleration_mps2),
            )

            # Cross(measured_up, desired_up): the small navigation-frame
            # rotation that moves the measured gravity direction toward up.
            correction_axis_navigation = (
                measured_up_navigation[1],
                -measured_up_navigation[0],
                0.0,
            )
            correction_rotation_vector = tuple(
                self._accelerometer_correction_gain_per_s
                * delta_time_s
                * component
                for component in correction_axis_navigation
            )

            correction = quaternion_from_rotation_vector(
                correction_rotation_vector
            )
            updated_orientation = normalize_quaternion(
                quaternion_multiply(correction, updated_orientation)
            )

        self._orientation_wxyz = updated_orientation
        self._last_timestamp_ns = sample.timestamp_ns

        return OrientationEstimate(
            timestamp_ns=sample.timestamp_ns,
            source=sample.source,
            source_id=sample.source_id,
            sensor_to_navigation_wxyz=self._orientation_wxyz,
        )
```

This is the actual orientation update:

1. Rejects anything not still in the raw sensor coordinate frame.
2. Uses the gyroscope to propagate orientation for the elapsed time.
3. Uses the accelerometer only when its magnitude is near gravity.
4. Applies a small tilt correction toward navigation up.
5. Returns the timestamped sensor-to-navigation quaternion.

It corrects roll and pitch. It does not solve absolute yaw; no magnetometer or GNSS heading has been supplied yet.

### `ImuOrientationEstimator.reset`

```python
    def reset(
        self,
        initial_orientation_wxyz: QuaternionWxyz | None = None,
    ) -> None:
        """Clear timing and source state after a confirmed sensor-session reset."""

        if initial_orientation_wxyz is not None:
            self._initial_orientation_wxyz = normalize_quaternion(
                initial_orientation_wxyz
            )

        self._orientation_wxyz = self._initial_orientation_wxyz
        self._last_timestamp_ns = None
        self._source = None
        self._source_id = None
```

Call this only after a genuine session restart, confirmed sensor gap, or deliberate reinitialization. It must not be called during normal driving just because the car turns or accelerates.

Final orientation flow:

```text
SynchronizedImuSample
    │
    ├── gyroscope × elapsed time
    │       │
    │       ▼
    │   propagate_orientation()
    │
    ├── accelerometer magnitude near gravity?
    │       │
    │       ├── no: keep gyro prediction
    │       │
    │       └── yes: rotate measured up into navigation frame
    │                    │
    │                    ▼
    │              small tilt correction
    │
    ▼
OrientationEstimate
(sensor → navigation quaternion)
    │
    ▼
phone-to-vehicle calibration
    │
    ▼
vehicle-frame rotation and gravity removal
```

Do not treat the yaw as true east/north until GNSS/EKF or another valid heading source seeds or corrects it. No tests yet, per our deterministic-stage testing plan.

> navigation_up is not defined and the next file now

<details><summary>1 previous message</summary>

> System error
>
> unexpected status 404 Not Found: Unknown error, url: https://chatgpt.com/backend-api/codex/responses, cf-ray: a355a2eb0c326080-DEL
</details>

> navigation\_up is not defined and the next file now

<details><summary>2 previous messages</summary>

> You’re right—that constant must be declared before the estimator uses it. Add the exact private constant below the imports, then we’ll move to the calibration file.
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/sensors/calibration.py`
>
> </details>
</details>

Add this directly below the imports in `orientation.py`:

```python
_NAVIGATION_UP: Vector3 = (0.0, 0.0, 1.0)
```

Then use the exact same name everywhere:

```python
_NAVIGATION_UP
```

Python treats `_NAVIGATION_UP`, `navigation_up`, and `NAVIGATION_UP` as completely different names.

Now we move to `calibration.py`.

Calibration is a different rotation from orientation:

```text
orientation:  sensor → navigation       changes as the phone moves
calibration:  sensor → vehicle FLU      mostly fixed until phone remounts
```

We first define how to apply an already-known calibration. Later, the dynamic calibrator will estimate that calibration from driving evidence.

Replace the imports in `calibration.py` with:

```python
from math import isfinite

from .orientation import rotate_vector
from .types import (
    CoordinateFrame,
    SynchronizedImuSample,
    VehicleCalibration,
)
```

Then add this first function:

```python
def rotate_imu_to_vehicle(
    sample: SynchronizedImuSample,
    calibration: VehicleCalibration,
    minimum_confidence: float,
) -> SynchronizedImuSample:
    """Rotate one synchronized SENSOR-frame IMU sample into vehicle FLU."""

    if not isfinite(minimum_confidence) or not 0.0 <= minimum_confidence <= 1.0:
        raise ValueError(
            "minimum_confidence must be finite and between 0.0 and 1.0."
        )

    if sample.frame is not CoordinateFrame.SENSOR:
        raise ValueError(
            "rotate_imu_to_vehicle expects a SENSOR-frame IMU sample."
        )

    if sample.source != calibration.source:
        raise ValueError(
            "Sample and calibration must belong to the same sensor source."
        )

    if sample.source_id != calibration.source_id:
        raise ValueError(
            "Sample and calibration must belong to the same physical device."
        )

    if calibration.timestamp_ns > sample.timestamp_ns:
        raise ValueError(
            "Cannot apply a calibration estimate to an earlier IMU sample."
        )

    if not isfinite(calibration.confidence) or not 0.0 <= calibration.confidence <= 1.0:
        raise ValueError(
            "Calibration confidence must be finite and between 0.0 and 1.0."
        )

    if calibration.confidence < minimum_confidence:
        raise ValueError(
            "Calibration confidence is below the required threshold."
        )

    return SynchronizedImuSample(
        timestamp_ns=sample.timestamp_ns,
        source=sample.source,
        source_id=sample.source_id,
        frame=CoordinateFrame.VEHICLE_FLU,
        acceleration_mps2=rotate_vector(
            calibration.sensor_to_vehicle_wxyz,
            sample.acceleration_mps2,
        ),
        angular_velocity_radps=rotate_vector(
            calibration.sensor_to_vehicle_wxyz,
            sample.angular_velocity_radps,
        ),
        accelerometer_timestamp_ns=sample.accelerometer_timestamp_ns,
        gyroscope_timestamp_ns=sample.gyroscope_timestamp_ns,
    )
```

What it does:

- Accepts a synchronized sensor-frame acceleration/gyro pair.
- Verifies that calibration belongs to that exact physical IMU.
- Prevents time travel: a calibration created later cannot alter an earlier sample.
- Refuses untrusted calibration rather than pretending arbitrary phone axes are vehicle axes.
- Rotates both acceleration and angular velocity into the vehicle’s Forward-Left-Up frame.
- Preserves timestamps for later diagnostics.

Small orientation cleanup: change `rotate_vector()`’s docstring to this, since calibration also uses it:

```python
"""Rotate a vector by a source-to-target quaternion."""
```

Next we’ll build the calibration evidence/state model that eventually produces `VehicleCalibration`.

> done next

<details><summary>2 previous messages</summary>

> Good. I’ll inspect only the calibration file you just updated, then we’ll add the calibration-state definition before writing the motion-evidence logic.
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/sensors/calibration.py`
>
> </details>
</details>

Next we define the deterministic math that turns two trustworthy mounting directions into a sensor-to-vehicle rotation.

Update the orientation imports in `calibration.py`:

```python
from .orientation import (
    normalize_quaternion,
    normalize_vector,
    quaternion_from_vector_alignment,
    quaternion_multiply,
    rotate_vector,
    vector_magnitude,
)
```

Add these imports too:

```python
from .types import (
    CoordinateFrame,
    QuaternionWxyz,
    SynchronizedImuSample,
    Vector3,
    VehicleCalibration,
)
```

Then add these constants below the imports:

```python
_VEHICLE_FORWARD: Vector3 = (1.0, 0.0, 0.0)
_VEHICLE_UP: Vector3 = (0.0, 0.0, 1.0)
```

Now add this function below `rotate_imu_to_vehicle()`:

```python
def derive_sensor_to_vehicle_quaternion(
    vehicle_up_in_sensor: Vector3,
    vehicle_forward_in_sensor: Vector3,
) -> QuaternionWxyz:
    """Derive a SENSOR-to-vehicle-FLU rotation from known mounting axes."""

    normalized_up_in_sensor = normalize_vector(vehicle_up_in_sensor)

    # First level the sensor: map the vehicle's up direction onto FLU up.
    sensor_to_level = quaternion_from_vector_alignment(
        normalized_up_in_sensor,
        _VEHICLE_UP,
    )

    # Express the known forward direction after leveling, then discard its
    # small remaining vertical component before resolving yaw.
    forward_in_level = rotate_vector(
        sensor_to_level,
        vehicle_forward_in_sensor,
    )
    horizontal_forward_in_level = (
        forward_in_level[0],
        forward_in_level[1],
        0.0,
    )

    if vector_magnitude(horizontal_forward_in_level) <= 1e-12:
        raise ValueError(
            "vehicle_forward_in_sensor must not be parallel to vehicle up."
        )

    normalized_horizontal_forward = normalize_vector(
        horizontal_forward_in_level
    )

    # A yaw-only rotation maps the leveled forward direction onto FLU forward.
    level_to_vehicle = quaternion_from_vector_alignment(
        normalized_horizontal_forward,
        _VEHICLE_FORWARD,
    )

    return normalize_quaternion(
        quaternion_multiply(level_to_vehicle, sensor_to_level)
    )
```

What it does:

1. `vehicle_up_in_sensor` is the vehicle’s upward direction expressed in phone axes. A stable accelerometer/gravity observation can provide this.
2. It first levels the phone so that vehicle up becomes FLU `z = up`.
3. `vehicle_forward_in_sensor` is the known positive forward direction in phone axes.
4. It removes the forward vector’s vertical noise, then applies only the remaining yaw rotation to make forward become FLU `x = forward`.
5. The final quaternion maps every sensor-frame vector directly into vehicle FLU.

This function intentionally does **not** guess forward direction. The upcoming calibration-state logic will collect enough acceleration/braking/GNSS evidence to supply a trustworthy signed `vehicle_forward_in_sensor`.

> okay next and all for this file, and detailed explanations of the functions too

<details><summary>2 previous messages</summary>

> I’ll finish the calibration file in this pass. I’ll first check the function you just added, then give the remaining calibration state machine and evidence-handling methods in order, with each method’s role explained.
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/sensors/calibration.py`
>
> </details>
</details>

Keep your two existing functions. To finish `calibration.py`, first update the top imports:

```python
from dataclasses import dataclass
from enum import StrEnum
from math import acos, isfinite, pi
```

Add `SensorSource` to the `.types` imports too.

Replace the module docstring with:

```python
"""Dynamic phone-to-vehicle calibration for the vehicle FLU frame.

Calibration is a mostly fixed SENSOR-to-vehicle rotation. It is estimated from
trusted mounting evidence, held while stable, and invalidated during a likely
phone remount. It never guesses a vehicle forward direction from arbitrary
single IMU readings.
"""
```

### `CalibrationPhase`

```python
class CalibrationPhase(StrEnum):
    """Current confidence state of one physical device's mounting estimate."""

    WARMING_UP = "warming_up"
    TRACKING = "tracking"
    DEGRADED = "degraded"
    RECALIBRATING = "recalibrating"
```

This makes calibration state explicit:

- `WARMING_UP`: gathering initial evidence.
- `TRACKING`: a stable calibration exists.
- `DEGRADED`: current calibration must not be trusted.
- `RECALIBRATING`: repeated evidence indicates a new mounting orientation.

### `CalibrationEvidence`

```python
@dataclass(frozen=True, slots=True)
class CalibrationEvidence:
    """One trustworthy observation of vehicle axes in sensor coordinates."""

    timestamp_ns: int
    source: SensorSource
    source_id: str

    # Vehicle up and known positive vehicle forward, both expressed in SENSOR
    # coordinates. They are not arbitrary raw acceleration vectors.
    vehicle_up_in_sensor: Vector3
    vehicle_forward_in_sensor: Vector3

    # Confidence in this individual observation, from 0.0 through 1.0.
    confidence: float
```

This is internal calibration input—not a raw sensor callback.

Later, the pipeline will derive:

- `vehicle_up_in_sensor` from trusted gravity observations.
- `vehicle_forward_in_sensor` from signed longitudinal evidence, such as GNSS-derived speed change aligned with sensor acceleration.

### `quaternion_angular_distance`

```python
def quaternion_angular_distance(
    left: QuaternionWxyz,
    right: QuaternionWxyz,
) -> float:
    """Return the smallest rotational difference between two quaternions."""

    left_unit = normalize_quaternion(left)
    right_unit = normalize_quaternion(right)

    alignment = abs(
        left_unit[0] * right_unit[0]
        + left_unit[1] * right_unit[1]
        + left_unit[2] * right_unit[2]
        + left_unit[3] * right_unit[3]
    )
    alignment = max(-1.0, min(1.0, alignment))

    return 2.0 * acos(alignment)
```

A quaternion and its negation represent the same physical rotation, which is why we use `abs()`.

The output is in radians:

```text
0.0          same mounting orientation
small value  minor noise or normal calibration variation
large value  possible phone remount
```

### `average_quaternions`

```python
def average_quaternions(
    weighted_quaternions: list[tuple[QuaternionWxyz, float]],
) -> QuaternionWxyz:
    """Return a confidence-weighted mean of mutually similar rotations."""

    if not weighted_quaternions:
        raise ValueError("At least one quaternion is required.")

    reference = normalize_quaternion(weighted_quaternions[0][0])

    total_w = 0.0
    total_x = 0.0
    total_y = 0.0
    total_z = 0.0
    total_weight = 0.0

    for quaternion, weight in weighted_quaternions:
        if not isfinite(weight) or weight <= 0.0:
            raise ValueError("Quaternion weights must be finite and positive.")

        w, x, y, z = normalize_quaternion(quaternion)

        # q and -q are identical rotations. Align signs before averaging so
        # they reinforce each other instead of cancelling toward zero.
        if (
            reference[0] * w
            + reference[1] * x
            + reference[2] * y
            + reference[3] * z
        ) < 0.0:
            w, x, y, z = -w, -x, -y, -z

        total_w += weight * w
        total_x += weight * x
        total_y += weight * y
        total_z += weight * z
        total_weight += weight

    if total_weight <= 0.0:
        raise ValueError("Total quaternion weight must be positive.")

    return normalize_quaternion(
        (
            total_w / total_weight,
            total_x / total_weight,
            total_y / total_weight,
            total_z / total_weight,
        )
    )
```

We do not trust one braking event or one gravity reading. This averages several consistent candidate mounting rotations, giving reliable observations greater influence.

### `DynamicVehicleCalibrator.__init__`

```python
class DynamicVehicleCalibrator:
    """Collect stable mounting evidence and publish safe vehicle calibration."""

    def __init__(
        self,
        *,
        minimum_evidence_count: int,
        minimum_evidence_confidence: float,
        maximum_disagreement_rad: float,
        remount_evidence_count: int,
    ) -> None:
        """Create a stateful calibrator for one physical IMU."""

        if minimum_evidence_count <= 0:
            raise ValueError("minimum_evidence_count must be positive.")

        if remount_evidence_count <= 0:
            raise ValueError("remount_evidence_count must be positive.")

        if (
            not isfinite(minimum_evidence_confidence)
            or not 0.0 <= minimum_evidence_confidence <= 1.0
        ):
            raise ValueError(
                "minimum_evidence_confidence must be between 0.0 and 1.0."
            )

        if (
            not isfinite(maximum_disagreement_rad)
            or not 0.0 < maximum_disagreement_rad <= pi
        ):
            raise ValueError(
                "maximum_disagreement_rad must be in the range (0, pi]."
            )

        self._minimum_evidence_count = minimum_evidence_count
        self._minimum_evidence_confidence = minimum_evidence_confidence
        self._maximum_disagreement_rad = maximum_disagreement_rad
        self._remount_evidence_count = remount_evidence_count
        self._maximum_retained_candidates = max(
            minimum_evidence_count,
            remount_evidence_count,
        ) * 2

        self._phase = CalibrationPhase.WARMING_UP
        self._source: SensorSource | None = None
        self._source_id: str | None = None
        self._last_timestamp_ns: int | None = None

        self._warmup_candidates: list[tuple[QuaternionWxyz, float]] = []
        self._stable_candidates: list[tuple[QuaternionWxyz, float]] = []
        self._remount_candidates: list[tuple[QuaternionWxyz, float]] = []
        self._calibration: VehicleCalibration | None = None
```

The constructor does not decide tuning values. They will come from device-specific configuration after we test real journeys.

It keeps three separate groups:

- Warm-up candidates for initial mounting discovery.
- Stable candidates that support the current calibration.
- Remount candidates that may prove the phone has moved.

### `phase` and `calibration`

```python
    @property
    def phase(self) -> CalibrationPhase:
        """Return the current calibration state."""

        return self._phase

    @property
    def calibration(self) -> VehicleCalibration | None:
        """Return the latest calibration, or None while still warming up."""

        return self._calibration
```

The pipeline can inspect these without mutating calibrator state.

### `_register_or_validate_evidence`

```python
    def _register_or_validate_evidence(
        self,
        evidence: CalibrationEvidence,
    ) -> None:
        """Validate ordering and bind this calibrator to one physical device."""

        if evidence.timestamp_ns < 0:
            raise ValueError("Calibration evidence timestamp must be non-negative.")

        if not evidence.source_id.strip():
            raise ValueError("Calibration evidence source_id must not be blank.")

        if (
            not isfinite(evidence.confidence)
            or not 0.0 <= evidence.confidence <= 1.0
        ):
            raise ValueError(
                "Calibration evidence confidence must be between 0.0 and 1.0."
            )

        if (
            self._last_timestamp_ns is not None
            and evidence.timestamp_ns <= self._last_timestamp_ns
        ):
            raise ValueError(
                "Calibration evidence timestamps must be strictly increasing."
            )

        if self._source is None:
            self._source = evidence.source
            self._source_id = evidence.source_id
        elif (
            evidence.source != self._source
            or evidence.source_id != self._source_id
        ):
            raise ValueError(
                "Cannot mix multiple physical IMUs in one DynamicVehicleCalibrator."
            )

        self._last_timestamp_ns = evidence.timestamp_ns
```

This repeats the one-device invariant from synchronization and orientation. A calibration is only meaningful for the phone or IMU that produced its evidence.

### `_append_if_consistent`

```python
    def _append_if_consistent(
        self,
        candidates: list[tuple[QuaternionWxyz, float]],
        candidate: QuaternionWxyz,
        confidence: float,
    ) -> bool:
        """Append a candidate only if it agrees with its existing cluster."""

        if candidates:
            cluster_orientation = average_quaternions(candidates)
            disagreement_rad = quaternion_angular_distance(
                candidate,
                cluster_orientation,
            )
            if disagreement_rad > self._maximum_disagreement_rad:
                return False

        candidates.append((candidate, confidence))

        if len(candidates) > self._maximum_retained_candidates:
            candidates.pop(0)

        return True
```

This is the outlier gate. A sudden, very different candidate should not rotate the vehicle frame immediately.

### `_confidence_from_candidates`

```python
    def _confidence_from_candidates(
        self,
        candidates: list[tuple[QuaternionWxyz, float]],
    ) -> float:
        """Calculate calibration confidence from evidence quality and agreement."""

        if not candidates:
            return 0.0

        mean_orientation = average_quaternions(candidates)
        total_weight = sum(weight for _, weight in candidates)

        mean_input_confidence = total_weight / len(candidates)
        mean_disagreement_rad = (
            sum(
                weight
                * quaternion_angular_distance(quaternion, mean_orientation)
                for quaternion, weight in candidates
            )
            / total_weight
        )

        agreement = max(
            0.0,
            1.0 - mean_disagreement_rad / self._maximum_disagreement_rad,
        )
        evidence_support = min(
            1.0,
            len(candidates) / self._minimum_evidence_count,
        )

        return min(
            1.0,
            mean_input_confidence * agreement * evidence_support,
        )
```

Final confidence requires three things:

```text
high-quality individual evidence
× agreement between observations
× enough observations
```

### `_publish_calibration`

```python
    def _publish_calibration(
        self,
        timestamp_ns: int,
    ) -> VehicleCalibration:
        """Build and retain a calibration from the current stable cluster."""

        if self._source is None or self._source_id is None:
            raise RuntimeError("Cannot publish calibration before source binding.")

        sensor_to_vehicle = average_quaternions(self._stable_candidates)
        confidence = self._confidence_from_candidates(
            self._stable_candidates
        )

        self._calibration = VehicleCalibration(
            timestamp_ns=timestamp_ns,
            source=self._source,
            source_id=self._source_id,
            sensor_to_vehicle_wxyz=sensor_to_vehicle,
            confidence=confidence,
        )
        return self._calibration
```

This is the only place that creates a `VehicleCalibration`. It always uses averaged, stable evidence rather than a raw observation.

### `_degrade_calibration`

```python
    def _degrade_calibration(
        self,
        timestamp_ns: int,
    ) -> VehicleCalibration | None:
        """Mark the latest calibration unusable while retaining its rotation."""

        if self._calibration is None:
            return None

        self._calibration = VehicleCalibration(
            timestamp_ns=timestamp_ns,
            source=self._calibration.source,
            source_id=self._calibration.source_id,
            sensor_to_vehicle_wxyz=self._calibration.sensor_to_vehicle_wxyz,
            confidence=0.0,
        )
        return self._calibration
```

If remount is suspected, keeping the old rotation with a normal confidence would be dangerous. A confidence of `0.0` ensures `rotate_imu_to_vehicle()` refuses it when the caller uses a sensible threshold.

### `update`

```python
    def update(
        self,
        evidence: CalibrationEvidence,
    ) -> VehicleCalibration | None:
        """Consume one evidence item and return the latest calibration state."""

        self._register_or_validate_evidence(evidence)

        if evidence.confidence < self._minimum_evidence_confidence:
            return self._degrade_calibration(evidence.timestamp_ns)

        candidate = derive_sensor_to_vehicle_quaternion(
            evidence.vehicle_up_in_sensor,
            evidence.vehicle_forward_in_sensor,
        )

        if self._calibration is None:
            accepted = self._append_if_consistent(
                self._warmup_candidates,
                candidate,
                evidence.confidence,
            )

            if not accepted:
                # Start a new possible initial cluster rather than mixing
                # incompatible mounting hypotheses.
                self._warmup_candidates = [(candidate, evidence.confidence)]

            if len(self._warmup_candidates) < self._minimum_evidence_count:
                self._phase = CalibrationPhase.WARMING_UP
                return None

            self._stable_candidates = list(self._warmup_candidates)
            self._warmup_candidates.clear()
            self._phase = CalibrationPhase.TRACKING
            return self._publish_calibration(evidence.timestamp_ns)

        disagreement_rad = quaternion_angular_distance(
            candidate,
            self._calibration.sensor_to_vehicle_wxyz,
        )

        if disagreement_rad <= self._maximum_disagreement_rad:
            self._append_if_consistent(
                self._stable_candidates,
                candidate,
                evidence.confidence,
            )
            self._remount_candidates.clear()
            self._phase = CalibrationPhase.TRACKING
            return self._publish_calibration(evidence.timestamp_ns)

        # A new candidate disagrees with the known mounting orientation.
        accepted_as_remount = self._append_if_consistent(
            self._remount_candidates,
            candidate,
            evidence.confidence,
        )

        if not accepted_as_remount:
            self._remount_candidates = [(candidate, evidence.confidence)]

        if len(self._remount_candidates) < self._remount_evidence_count:
            self._phase = (
                CalibrationPhase.RECALIBRATING
                if len(self._remount_candidates) > 1
                else CalibrationPhase.DEGRADED
            )
            return self._degrade_calibration(evidence.timestamp_ns)

        # Several mutually consistent observations support a new mounting.
        self._stable_candidates = list(self._remount_candidates)
        self._remount_candidates.clear()
        self._phase = CalibrationPhase.TRACKING
        return self._publish_calibration(evidence.timestamp_ns)
```

This is the full state machine:

- In warm-up, it waits for enough mutually consistent evidence.
- In tracking, compatible evidence refines calibration.
- A conflicting observation first degrades calibration.
- Repeated, mutually consistent conflicting observations prove a remount.
- It then promotes the new cluster to tracking calibration.

### `reset`

```python
    def reset(self) -> None:
        """Forget calibration state after a confirmed device-session restart."""

        self._phase = CalibrationPhase.WARMING_UP
        self._source = None
        self._source_id = None
        self._last_timestamp_ns = None
        self._warmup_candidates.clear()
        self._stable_candidates.clear()
        self._remount_candidates.clear()
        self._calibration = None
```

Use this only for a new device session or an intentional full restart. Normal remounts are handled by `update()`.

Final calibration flow:

```text
trusted gravity + signed forward-motion evidence
                    │
                    ▼
           CalibrationEvidence
                    │
                    ▼
    DynamicVehicleCalibrator.update()
                    │
       ┌────────────┼────────────┐
       ▼            ▼            ▼
   warm-up      tracking      remount
   no output    calibration   degraded → recalibrated
                    │
                    ▼
            VehicleCalibration
                    │
                    ▼
rotate_imu_to_vehicle()
                    │
                    ▼
SynchronizedImuSample in VEHICLE_FLU
                    │
                    ▼
gravity_removal.py
```

No tests yet; this completes the initial calibration file design.

> done, add explanatory comments if you want to in any of the files anywhere, then next

<details><summary>6 previous messages</summary>

> I’ll add only high-value explanatory comments to the current orientation and calibration files—at the frame-transform and state-transition boundaries—then move to gravity removal. I’ll keep the actual test run deferred.
>
> <details><summary>Explored 2 files</summary>
>
> - Read `./src/idr_backend/sensors/calibration.py`
> - Read `./src/idr_backend/sensors/orientation.py`
>
> </details>
>
> I found two real blockers while reviewing the current files: `SensorSource` is missing from calibration imports, and `update()` was accidentally indented inside an orientation helper instead of being a class method. I’ll fix those alongside the existing explanatory comments, without running tests yet.
>
> <details><summary>Edited 2 files</summary>
>
> - Wrote `./src/idr_backend/sensors/calibration.py` (+2 -1)
> - Wrote `./src/idr_backend/sensors/orientation.py` (+79 -79)
>
> </details>
>
> Those two blockers are corrected, and the existing comments already cover the important rotation and state-machine decisions. Next is gravity removal: it consumes the calibrated vehicle-frame IMU reading plus the vehicle-to-navigation orientation.
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/sensors/gravity_removal.py`
>
> </details>
</details>

I corrected the two blockers:

- `SensorSource` is now imported in `calibration.py`.
- `ImuOrientationEstimator.update()` is now correctly a class method, not accidentally nested inside `_register_or_validate_stream()`.

Next is [gravity_removal.py](</E:/dead reckoning/src/idr_backend/sensors/gravity_removal.py).

First, replace its docstring with:

```python
"""Gravity compensation for calibrated vehicle-frame IMU data.

An accelerometer measures specific force, not linear acceleration directly.
This module uses the vehicle-to-navigation orientation to express local gravity
in vehicle FLU, then adds it back to recover vehicle linear acceleration.
"""
```

Add these imports:

```python
from .orientation import (
    normalize_quaternion,
    quaternion_conjugate,
    quaternion_multiply,
)
from .types import (
    OrientationEstimate,
    QuaternionWxyz,
    VehicleCalibration,
)
```

Then add this first function:

```python
def derive_vehicle_to_navigation_quaternion(
    orientation: OrientationEstimate,
    calibration: VehicleCalibration,
) -> QuaternionWxyz:
    """Compose SENSOR-to-navigation and SENSOR-to-vehicle rotations."""

    if orientation.source != calibration.source:
        raise ValueError(
            "Orientation and calibration must belong to the same sensor source."
        )

    if orientation.source_id != calibration.source_id:
        raise ValueError(
            "Orientation and calibration must belong to the same physical device."
        )

    if calibration.timestamp_ns > orientation.timestamp_ns:
        raise ValueError(
            "Cannot use a calibration estimate newer than the orientation sample."
        )

    # SENSOR -> NAVIGATION, composed with VEHICLE -> SENSOR.
    # The inverse of SENSOR -> VEHICLE is VEHICLE -> SENSOR.
    vehicle_to_sensor = quaternion_conjugate(
        calibration.sensor_to_vehicle_wxyz
    )

    return normalize_quaternion(
        quaternion_multiply(
            orientation.sensor_to_navigation_wxyz,
            vehicle_to_sensor,
        )
    )
```

Why this exists:

```text
q_sensor_to_navigation: SENSOR  → navigation
q_sensor_to_vehicle:    SENSOR  → vehicle

inverse(q_sensor_to_vehicle):   vehicle → SENSOR
```

So the complete route is:

```text
vehicle vector
    │
    ▼ inverse calibration
sensor vector
    │
    ▼ orientation
navigation vector
```

Mathematically:

```text
q_vehicle_to_navigation
    = q_sensor_to_navigation ⊗ inverse(q_sensor_to_vehicle)
```

This quaternion is needed next to rotate navigation gravity `(0, 0, -g)` into vehicle FLU before removing it from the calibrated accelerometer reading.

> next

<details><summary>2 previous messages</summary>

> Next we’ll implement the actual gravity compensation step: convert gravity from navigation ENU into vehicle FLU, then add it to the accelerometer’s specific force to obtain linear acceleration.
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/sensors/gravity_removal.py`
>
> </details>
</details>

Add `isfinite` to imports:

```python
from math import isfinite
```

Add `rotate_vector` to the orientation imports and `Vector3` to the types imports.

Then add this below `derive_vehicle_to_navigation_quaternion()`:

```python
def gravity_vector_in_vehicle_frame(
    vehicle_to_navigation_wxyz: QuaternionWxyz,
    gravity_mps2: float = 9.80665,
) -> Vector3:
    """Express navigation gravity in the vehicle Forward-Left-Up frame."""

    if not isfinite(gravity_mps2) or gravity_mps2 <= 0.0:
        raise ValueError("gravity_mps2 must be finite and positive.")

    # Gravity points down in navigation ENU: z = -g.
    gravity_in_navigation: Vector3 = (0.0, 0.0, -gravity_mps2)

    # vehicle_to_navigation maps vehicle vectors into ENU. Its inverse maps
    # ENU vectors, including gravity, back into vehicle FLU.
    navigation_to_vehicle = quaternion_conjugate(
        normalize_quaternion(vehicle_to_navigation_wxyz)
    )

    return rotate_vector(
        navigation_to_vehicle,
        gravity_in_navigation,
    )
```

What it does:

```text
gravity in ENU               = (0, 0, -9.80665)
vehicle-to-navigation q      = vehicle → ENU
inverse(q)                   = ENU → vehicle
gravity in vehicle FLU       = inverse(q) × gravity_ENU
```

For a level vehicle:

```text
gravity_in_vehicle = (0, 0, -9.80665)
accelerometer      = (0, 0, +9.80665)   # stationary specific force
linear acceleration = accelerometer + gravity = (0, 0, 0)
```

The next function will perform exactly that final addition and construct `VehicleImuSample` for the velocity model.

> okay next and all for this file, and detailed explanations of the functions too

<details><summary>2 previous messages</summary>

> I’ll finish gravity removal in this pass: the final compensation function, its validation boundaries, and the complete handoff into `VehicleImuSample`.
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/sensors/gravity_removal.py`
>
> </details>
</details>

Finish `gravity_removal.py` with these imports:

```python
from math import isfinite

from .orientation import (
    normalize_quaternion,
    quaternion_conjugate,
    quaternion_multiply,
    rotate_vector,
)
from .types import (
    CoordinateFrame,
    OrientationEstimate,
    QuaternionWxyz,
    SynchronizedImuSample,
    Vector3,
    VehicleCalibration,
    VehicleImuSample,
)
```

Your existing `derive_vehicle_to_navigation_quaternion()` is the first stage. It composes:

```text
vehicle → sensor → navigation
```

and returns the orientation needed for navigation/fusion output.

### `gravity_vector_in_vehicle_frame`

Add this next:

```python
def gravity_vector_in_vehicle_frame(
    vehicle_to_navigation_wxyz: QuaternionWxyz,
    gravity_mps2: float = 9.80665,
) -> Vector3:
    """Express navigation gravity in the vehicle Forward-Left-Up frame."""

    if not isfinite(gravity_mps2) or gravity_mps2 <= 0.0:
        raise ValueError("gravity_mps2 must be finite and positive.")

    # ENU is East-North-Up, so physical gravity points along negative z.
    gravity_in_navigation: Vector3 = (0.0, 0.0, -gravity_mps2)

    # Invert vehicle → navigation to transform the gravity vector back into
    # vehicle Forward-Left-Up coordinates.
    navigation_to_vehicle = quaternion_conjugate(
        normalize_quaternion(vehicle_to_navigation_wxyz)
    )

    return rotate_vector(
        navigation_to_vehicle,
        gravity_in_navigation,
    )
```

An accelerometer measures specific force, not linear acceleration:

```text
specific force = linear acceleration - gravity
linear acceleration = specific force + gravity
```

For a parked level vehicle:

```text
specific force in FLU = (0, 0, +9.80665)
gravity in FLU        = (0, 0, -9.80665)
linear acceleration   = (0, 0, 0)
```

### `remove_gravity_from_vehicle_imu`

Add this final function:

```python
def remove_gravity_from_vehicle_imu(
    vehicle_sample: SynchronizedImuSample,
    orientation: OrientationEstimate,
    calibration: VehicleCalibration,
    gravity_mps2: float = 9.80665,
) -> VehicleImuSample:
    """Produce cleaned vehicle-frame IMU data for velocity prediction."""

    if vehicle_sample.frame is not CoordinateFrame.VEHICLE_FLU:
        raise ValueError(
            "Gravity removal expects a VEHICLE_FLU-frame IMU sample."
        )

    if (
        vehicle_sample.source != orientation.source
        or vehicle_sample.source_id != orientation.source_id
    ):
        raise ValueError(
            "Vehicle sample and orientation must belong to the same device."
        )

    if (
        vehicle_sample.source != calibration.source
        or vehicle_sample.source_id != calibration.source_id
    ):
        raise ValueError(
            "Vehicle sample and calibration must belong to the same device."
        )

    if orientation.timestamp_ns != vehicle_sample.timestamp_ns:
        raise ValueError(
            "Orientation and vehicle IMU sample must have the same timestamp."
        )

    if calibration.timestamp_ns > vehicle_sample.timestamp_ns:
        raise ValueError(
            "Calibration must not be newer than the vehicle IMU sample."
        )

    if (
        not isfinite(calibration.confidence)
        or not 0.0 <= calibration.confidence <= 1.0
    ):
        raise ValueError(
            "Calibration confidence must be finite and between 0.0 and 1.0."
        )

    vehicle_to_navigation = derive_vehicle_to_navigation_quaternion(
        orientation,
        calibration,
    )
    gravity_in_vehicle = gravity_vector_in_vehicle_frame(
        vehicle_to_navigation,
        gravity_mps2,
    )

    # Accelerometer values are specific force. Adding the correctly oriented
    # gravity vector recovers the vehicle's physical linear acceleration.
    linear_acceleration_mps2 = (
        vehicle_sample.acceleration_mps2[0] + gravity_in_vehicle[0],
        vehicle_sample.acceleration_mps2[1] + gravity_in_vehicle[1],
        vehicle_sample.acceleration_mps2[2] + gravity_in_vehicle[2],
    )

    return VehicleImuSample(
        timestamp_ns=vehicle_sample.timestamp_ns,
        source=vehicle_sample.source,
        source_id=vehicle_sample.source_id,
        linear_acceleration_mps2=linear_acceleration_mps2,
        angular_velocity_radps=vehicle_sample.angular_velocity_radps,
        vehicle_to_navigation_wxyz=vehicle_to_navigation,
        calibration_confidence=calibration.confidence,
    )
```

This is the deterministic preprocessing output. It retains:

- Gravity-free acceleration in vehicle FLU.
- Gyroscope data in vehicle FLU.
- Vehicle-to-navigation orientation for later EKF fusion.
- Calibration confidence for the velocity model, uncertainty engine, and fusion gates.

Final flow:

```text
Synchronized SENSOR-frame IMU
    │
    ▼ orientation.py
OrientationEstimate: SENSOR → navigation
    │
    ▼ calibration.py
Synchronized VEHICLE_FLU IMU
    │
    ▼ derive vehicle → navigation
    │
    ▼ rotate ENU gravity into vehicle FLU
    │
    ▼ specific force + gravity
VehicleImuSample
    │
    ▼ fixed-rate resampling / causal window buffer
    │
    ▼ velocity predictor
```

That completes the initial gravity-removal file.

> next file now, detailed explanations of the functions, and the full file at once, fn snippet then expln then fn snippet and so on

<details><summary>2 previous messages</summary>

> Next is `quality.py`. It closes the deterministic sensor stage by turning timing, calibration, and physical plausibility into explicit quality signals that later gate the velocity model and EKF. I’ll give the complete initial file in the requested function-by-function format.
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/sensors/quality.py`
>
> </details>
</details>

Replace all of `quality.py` with this initial deterministic quality monitor. It reports observable input problems; it does not pretend to estimate statistical uncertainty—that belongs to the uncertainty engine later.

```python
"""Deterministic quality checks for cleaned vehicle-frame IMU data.

This module reports observable timing, plausibility, and calibration problems.
It does not estimate velocity uncertainty or covariance; downstream uncertainty
and fusion components consume these explicit quality facts and apply their own
policies.
"""

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite, sqrt

from .types import SensorSource, Vector3, VehicleImuSample
```

### `QualityFlag`

```python
class QualityFlag(StrEnum):
    """Observable reasons why one cleaned IMU sample may be unsafe to use."""

    NONFINITE_LINEAR_ACCELERATION = "nonfinite_linear_acceleration"
    NONFINITE_ANGULAR_VELOCITY = "nonfinite_angular_velocity"
    TIMESTAMP_REGRESSION = "timestamp_regression"
    SENSOR_GAP = "sensor_gap"
    LINEAR_ACCELERATION_LIMIT_EXCEEDED = (
        "linear_acceleration_limit_exceeded"
    )
    ANGULAR_VELOCITY_LIMIT_EXCEEDED = (
        "angular_velocity_limit_exceeded"
    )
    CALIBRATION_CONFIDENCE_INVALID = "calibration_confidence_invalid"
    CALIBRATION_CONFIDENCE_LOW = "calibration_confidence_low"
```

A flag is a fact, not a guess. For example, `SENSOR_GAP` means the input arrived too late for a contiguous velocity-model window; it does not say why the gap happened.

### `VehicleImuQuality`

```python
@dataclass(frozen=True, slots=True)
class VehicleImuQuality:
    """Quality facts associated with one cleaned vehicle-frame IMU sample."""

    timestamp_ns: int
    source: SensorSource
    source_id: str

    flags: frozenset[QualityFlag]
    sample_interval_ns: int | None

    # Transparent deterministic summary: zero for hard failures; otherwise
    # derived from calibration confidence. It is not an uncertainty variance.
    score: float

    # True only when no configured deterministic gate has failed.
    is_acceptable: bool
```

This is what the later velocity adapter, uncertainty engine, and EKF can consume.

`sample_interval_ns` is `None` for the first reading because there is no previous timestamp to compare with.

### `VehicleImuQualityLimits`

```python
@dataclass(frozen=True, slots=True)
class VehicleImuQualityLimits:
    """Configured physical and timing boundaries for one IMU source."""

    max_gap_ns: int
    max_linear_acceleration_mps2: float
    max_angular_velocity_radps: float
    minimum_calibration_confidence: float
```

These limits must eventually come from device configuration, not hard-coded assumptions. A phone, external IMU, and replay dataset may have different valid ranges.

### `_vector_is_finite`

```python
def _vector_is_finite(vector: Vector3) -> bool:
    """Return whether every component of a vector is finite."""

    return all(isfinite(component) for component in vector)
```

This is deliberately tiny. Invalid values must be detected before calculating magnitudes, because NaN and infinity can otherwise spread through the whole pipeline.

### `_vector_magnitude`

```python
def _vector_magnitude(vector: Vector3) -> float:
    """Return the Euclidean magnitude of a finite vector."""

    if not _vector_is_finite(vector):
        raise ValueError("Vector components must all be finite.")

    x, y, z = vector
    return sqrt(x * x + y * y + z * z)
```

We compare vector magnitude with configured physical limits rather than separately limiting each axis. That works regardless of the phone’s mounting orientation.

### `_quality_score`

```python
def _quality_score(
    flags: frozenset[QualityFlag],
    calibration_confidence: float,
) -> float:
    """Return a transparent deterministic score from flags and confidence."""

    hard_failure_flags = {
        QualityFlag.NONFINITE_LINEAR_ACCELERATION,
        QualityFlag.NONFINITE_ANGULAR_VELOCITY,
        QualityFlag.TIMESTAMP_REGRESSION,
        QualityFlag.SENSOR_GAP,
        QualityFlag.LINEAR_ACCELERATION_LIMIT_EXCEEDED,
        QualityFlag.ANGULAR_VELOCITY_LIMIT_EXCEEDED,
        QualityFlag.CALIBRATION_CONFIDENCE_INVALID,
    }

    if flags & hard_failure_flags:
        return 0.0

    return calibration_confidence
```

This intentionally avoids inventing an opaque “AI quality score.”

- Hard failures produce `0.0`.
- Otherwise, the score equals the calibration confidence.
- Low calibration confidence is preserved numerically, but `is_acceptable` becomes `False` through its flag.

### `VehicleImuQualityMonitor.__init__`

```python
class VehicleImuQualityMonitor:
    """Assess one chronological stream of cleaned vehicle-frame IMU samples."""

    def __init__(
        self,
        limits: VehicleImuQualityLimits,
    ) -> None:
        """Create a monitor with explicit device-specific limits."""

        if limits.max_gap_ns <= 0:
            raise ValueError("max_gap_ns must be positive.")

        if (
            not isfinite(limits.max_linear_acceleration_mps2)
            or limits.max_linear_acceleration_mps2 <= 0.0
        ):
            raise ValueError(
                "max_linear_acceleration_mps2 must be finite and positive."
            )

        if (
            not isfinite(limits.max_angular_velocity_radps)
            or limits.max_angular_velocity_radps <= 0.0
        ):
            raise ValueError(
                "max_angular_velocity_radps must be finite and positive."
            )

        if (
            not isfinite(limits.minimum_calibration_confidence)
            or not 0.0 <= limits.minimum_calibration_confidence <= 1.0
        ):
            raise ValueError(
                "minimum_calibration_confidence must be between 0.0 and 1.0."
            )

        self._limits = limits
        self._source: SensorSource | None = None
        self._source_id: str | None = None
        self._last_timestamp_ns: int | None = None
```

One monitor belongs to one device, just like the synchronizer, orientation estimator, and calibrator.

### `_register_or_validate_stream`

```python
    def _register_or_validate_stream(
        self,
        sample: VehicleImuSample,
    ) -> None:
        """Bind the monitor to one device and reject accidental stream mixing."""

        if self._source is None:
            self._source = sample.source
            self._source_id = sample.source_id
            return

        if (
            sample.source != self._source
            or sample.source_id != self._source_id
        ):
            raise ValueError(
                "Cannot mix multiple physical IMU streams in one "
                "VehicleImuQualityMonitor."
            )
```

If phone and external-IMU streams exist later, each receives a separate monitor. Combining their timestamps or quality histories would be invalid.

### `assess`

```python
    def assess(
        self,
        sample: VehicleImuSample,
    ) -> VehicleImuQuality:
        """Assess one cleaned vehicle-frame sample without altering its values."""

        self._register_or_validate_stream(sample)

        flags: set[QualityFlag] = set()
        sample_interval_ns: int | None = None

        if not _vector_is_finite(sample.linear_acceleration_mps2):
            flags.add(QualityFlag.NONFINITE_LINEAR_ACCELERATION)
        elif (
            _vector_magnitude(sample.linear_acceleration_mps2)
            > self._limits.max_linear_acceleration_mps2
        ):
            flags.add(QualityFlag.LINEAR_ACCELERATION_LIMIT_EXCEEDED)

        if not _vector_is_finite(sample.angular_velocity_radps):
            flags.add(QualityFlag.NONFINITE_ANGULAR_VELOCITY)
        elif (
            _vector_magnitude(sample.angular_velocity_radps)
            > self._limits.max_angular_velocity_radps
        ):
            flags.add(QualityFlag.ANGULAR_VELOCITY_LIMIT_EXCEEDED)

        if self._last_timestamp_ns is not None:
            if sample.timestamp_ns <= self._last_timestamp_ns:
                flags.add(QualityFlag.TIMESTAMP_REGRESSION)
            else:
                sample_interval_ns = (
                    sample.timestamp_ns - self._last_timestamp_ns
                )
                if sample_interval_ns > self._limits.max_gap_ns:
                    flags.add(QualityFlag.SENSOR_GAP)

        # Do not move the reference time backward after an invalid timestamp.
        if (
            self._last_timestamp_ns is None
            or sample.timestamp_ns > self._last_timestamp_ns
        ):
            self._last_timestamp_ns = sample.timestamp_ns

        calibration_confidence = sample.calibration_confidence
        if (
            not isfinite(calibration_confidence)
            or not 0.0 <= calibration_confidence <= 1.0
        ):
            flags.add(QualityFlag.CALIBRATION_CONFIDENCE_INVALID)
            calibration_confidence = 0.0
        elif (
            calibration_confidence
            < self._limits.minimum_calibration_confidence
        ):
            flags.add(QualityFlag.CALIBRATION_CONFIDENCE_LOW)

        frozen_flags = frozenset(flags)

        return VehicleImuQuality(
            timestamp_ns=sample.timestamp_ns,
            source=sample.source,
            source_id=sample.source_id,
            flags=frozen_flags,
            sample_interval_ns=sample_interval_ns,
            score=_quality_score(
                frozen_flags,
                calibration_confidence,
            ),
            is_acceptable=not frozen_flags,
        )
```

`assess()` never edits the IMU values. It only records what is safe or unsafe about them.

Its order is important:

1. Check numerical validity before magnitude.
2. Check physical magnitude limits.
3. Compare timestamp with prior input.
4. Preserve monotonic monitor state even after a gap.
5. Validate calibration confidence.
6. Return immutable quality facts.

### `reset`

```python
    def reset(self) -> None:
        """Forget timing and source state after a confirmed session restart."""

        self._source = None
        self._source_id = None
        self._last_timestamp_ns = None
```

Call this only after a known sensor-session restart. A normal gap should be reported as `SENSOR_GAP`, not erased.

Final quality flow:

```text
VehicleImuSample
    │
    ├── finite-vector checks
    ├── physical-magnitude checks
    ├── timestamp-gap checks
    └── calibration-confidence checks
    │
    ▼
VehicleImuQuality
    │
    ├── velocity window builder: reject broken windows
    ├── uncertainty engine: use flags and score as features
    └── EKF: gate unsafe measurement updates
```

This completes the initial quality file. The next deterministic piece is fixed-rate resampling and causal window construction for the velocity model.

> yes lets do it

<details><summary>2 previous messages</summary>

> We’ll add a new `sensors/resampling.py` file. The GRU needs a fixed-rate sequence; synchronized phone callbacks are not guaranteed to arrive at exactly the training rate, so resampling must happen after gravity removal and quality checks but before the velocity-model window buffer.
>
> <details><summary>Ran a command</summary>
>
> - Ran `Test-Path -LiteralPath 'src/idr_backend/sensors/resampling.py'; Get-Content -LiteralPath 'src/idr_backend/sensors/__init__.py'`
>
> </details>
</details>

Create [resampling.py](</E:/dead reckoning/src/idr_backend/sensors/resampling.py>) with:

```python
"""Causal fixed-rate resampling for cleaned vehicle-frame IMU data.

Velocity models require evenly spaced inputs, but sensor callbacks can jitter or
arrive at a different rate. This module resamples only between consecutive
acceptable samples and never bridges a quality failure or sensor gap.
"""
```

Add:

```python
from math import isfinite

from .types import Vector3
```

Then write the first internal helper:

```python
def _interpolate_vector(
    before: Vector3,
    after: Vector3,
    fraction: float,
) -> Vector3:
    """Linearly interpolate a finite vector from before toward after."""

    if not isfinite(fraction) or not 0.0 <= fraction <= 1.0:
        raise ValueError("fraction must be finite and between 0.0 and 1.0.")

    if not all(isfinite(component) for component in (*before, *after)):
        raise ValueError("Interpolation vectors must contain only finite values.")

    return (
        before[0] + fraction * (after[0] - before[0]),
        before[1] + fraction * (after[1] - before[1]),
        before[2] + fraction * (after[2] - before[2]),
    )
```

What it does:

```text
fraction = 0.0  → exactly the earlier vector
fraction = 1.0  → exactly the later vector
fraction = 0.5  → midpoint between both vectors
```

For example, if cleaned forward acceleration changes from `0` to `2 m/s²` between two real samples, a target resampling instant halfway between them receives `1 m/s²`.

This helper is only for acceleration and gyroscope vectors. Orientation quaternions need spherical interpolation, which we will handle separately so we never linearly blend rotations incorrectly.

> done, detailed explanations of the functions, and the full file at once, fn snippet then expln then fn snippet and so on

<details><summary>2 previous messages</summary>

> I’ll finish `resampling.py` now: quaternion interpolation, whole-sample interpolation, and the stateful fixed-rate resampler. Each function will stay separate with its own explanation.
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/sensors/resampling.py`
>
> </details>
</details>

Keep `_interpolate_vector()`. Finish `resampling.py` by updating the imports to:

```python
from math import acos, isfinite, sin

from .orientation import normalize_quaternion
from .quality import VehicleImuQuality
from .types import (
    QuaternionWxyz,
    SensorSource,
    Vector3,
    VehicleImuSample,
)
```

### `_interpolate_quaternion`

```python
def _interpolate_quaternion(
    before: QuaternionWxyz,
    after: QuaternionWxyz,
    fraction: float,
) -> QuaternionWxyz:
    """Spherically interpolate two unit rotation quaternions."""

    if not isfinite(fraction) or not 0.0 <= fraction <= 1.0:
        raise ValueError("fraction must be finite and between 0.0 and 1.0.")

    before_unit = normalize_quaternion(before)
    after_unit = normalize_quaternion(after)

    dot_product = (
        before_unit[0] * after_unit[0]
        + before_unit[1] * after_unit[1]
        + before_unit[2] * after_unit[2]
        + before_unit[3] * after_unit[3]
    )

    # q and -q represent the same rotation. Negating one chooses the shortest
    # rotational path instead of taking the long way around the quaternion sphere.
    if dot_product < 0.0:
        after_unit = (
            -after_unit[0],
            -after_unit[1],
            -after_unit[2],
            -after_unit[3],
        )
        dot_product = -dot_product

    dot_product = max(-1.0, min(1.0, dot_product))

    # Nearly identical rotations are numerically safer with linear blending.
    if dot_product > 0.9995:
        return normalize_quaternion(
            (
                before_unit[0] + fraction * (after_unit[0] - before_unit[0]),
                before_unit[1] + fraction * (after_unit[1] - before_unit[1]),
                before_unit[2] + fraction * (after_unit[2] - before_unit[2]),
                before_unit[3] + fraction * (after_unit[3] - before_unit[3]),
            )
        )

    angle_rad = acos(dot_product)
    sin_angle = sin(angle_rad)

    before_weight = sin((1.0 - fraction) * angle_rad) / sin_angle
    after_weight = sin(fraction * angle_rad) / sin_angle

    return normalize_quaternion(
        (
            before_weight * before_unit[0] + after_weight * after_unit[0],
            before_weight * before_unit[1] + after_weight * after_unit[1],
            before_weight * before_unit[2] + after_weight * after_unit[2],
            before_weight * before_unit[3] + after_weight * after_unit[3],
        )
    )
```

Acceleration and gyro vectors can be linearly interpolated because they are ordinary numeric measurements. Rotations cannot: linearly mixing quaternions can create invalid or non-uniform rotations.

This function uses SLERP—spherical linear interpolation—so the orientation follows the shortest smooth rotational path.

### `_interpolate_vehicle_imu_sample`

```python
def _interpolate_vehicle_imu_sample(
    before: VehicleImuSample,
    after: VehicleImuSample,
    timestamp_ns: int,
) -> VehicleImuSample:
    """Create one fixed-rate vehicle IMU sample between two real samples."""

    if before.source != after.source or before.source_id != after.source_id:
        raise ValueError(
            "Cannot interpolate samples from different physical IMU devices."
        )

    if after.timestamp_ns <= before.timestamp_ns:
        raise ValueError(
            "Interpolation requires strictly increasing sample timestamps."
        )

    if not before.timestamp_ns <= timestamp_ns <= after.timestamp_ns:
        raise ValueError(
            "Interpolation timestamp must lie between the input timestamps."
        )

    fraction = (
        (timestamp_ns - before.timestamp_ns)
        / (after.timestamp_ns - before.timestamp_ns)
    )

    return VehicleImuSample(
        timestamp_ns=timestamp_ns,
        source=before.source,
        source_id=before.source_id,
        linear_acceleration_mps2=_interpolate_vector(
            before.linear_acceleration_mps2,
            after.linear_acceleration_mps2,
            fraction,
        ),
        angular_velocity_radps=_interpolate_vector(
            before.angular_velocity_radps,
            after.angular_velocity_radps,
            fraction,
        ),
        vehicle_to_navigation_wxyz=_interpolate_quaternion(
            before.vehicle_to_navigation_wxyz,
            after.vehicle_to_navigation_wxyz,
            fraction,
        ),
        # An interpolated result cannot be more trustworthy than either real
        # sample that produced it.
        calibration_confidence=min(
            before.calibration_confidence,
            after.calibration_confidence,
        ),
    )
```

This turns two real cleaned readings into one evenly timed reading.

The important safety decision is:

```text
interpolated confidence = min(before confidence, after confidence)
```

We never create extra confidence merely by filling a timestamp gap.

### `FixedRateVehicleImuResampler.__init__`

```python
class FixedRateVehicleImuResampler:
    """Causally resample one acceptable vehicle IMU stream at a fixed period."""

    def __init__(
        self,
        target_period_ns: int,
    ) -> None:
        """Create a resampler whose output grid begins at its first sample."""

        if target_period_ns <= 0:
            raise ValueError("target_period_ns must be positive.")

        self._target_period_ns = target_period_ns
        self._source: SensorSource | None = None
        self._source_id: str | None = None
        self._last_received_timestamp_ns: int | None = None
        self._previous_sample: VehicleImuSample | None = None
        self._next_output_timestamp_ns: int | None = None
```

For the teammate’s current GRU:

```text
target_period_ns = 100_000_000     # 10 Hz
```

The final value must come from our trained model manifest, not be hard-coded in the pipeline.

### `_register_or_validate_stream`

```python
    def _register_or_validate_stream(
        self,
        sample: VehicleImuSample,
    ) -> None:
        """Bind this resampler to one physical IMU stream."""

        if self._source is None:
            self._source = sample.source
            self._source_id = sample.source_id
            return

        if (
            sample.source != self._source
            or sample.source_id != self._source_id
        ):
            raise ValueError(
                "Cannot mix multiple physical IMU streams in one resampler."
            )
```

A resampling grid belongs to exactly one device. A phone and external IMU need separate grids.

### `push`

```python
    def push(
        self,
        sample: VehicleImuSample,
        quality: VehicleImuQuality,
    ) -> tuple[VehicleImuSample, ...]:
        """Accept one cleaned sample and emit any newly available grid samples."""

        if (
            quality.timestamp_ns != sample.timestamp_ns
            or quality.source != sample.source
            or quality.source_id != sample.source_id
        ):
            raise ValueError(
                "Quality report must belong to the exact vehicle IMU sample."
            )

        self._register_or_validate_stream(sample)

        if (
            self._last_received_timestamp_ns is not None
            and sample.timestamp_ns <= self._last_received_timestamp_ns
        ):
            raise ValueError(
                "Resampler input timestamps must be strictly increasing."
            )

        self._last_received_timestamp_ns = sample.timestamp_ns

        # Never interpolate across a sensor gap, invalid value, or poor
        # calibration. The next acceptable sample starts a fresh window.
        if not quality.is_acceptable:
            self._previous_sample = None
            self._next_output_timestamp_ns = None
            return ()

        if self._previous_sample is None:
            self._previous_sample = sample
            self._next_output_timestamp_ns = (
                sample.timestamp_ns + self._target_period_ns
            )

            # The first accepted real sample anchors this new fixed-rate grid.
            return (sample,)

        output_samples: list[VehicleImuSample] = []

        while (
            self._next_output_timestamp_ns is not None
            and self._next_output_timestamp_ns <= sample.timestamp_ns
        ):
            output_samples.append(
                _interpolate_vehicle_imu_sample(
                    self._previous_sample,
                    sample,
                    self._next_output_timestamp_ns,
                )
            )
            self._next_output_timestamp_ns += self._target_period_ns

        self._previous_sample = sample

        return tuple(output_samples)
```

`push()` is causal:

```text
previous real sample ────── current real sample
                ↑
        output grid points emitted only after
        the current right-hand sample arrives
```

It never invents values across quality failures. A broken input resets the grid, so the future GRU cannot unknowingly receive a window spanning an IMU gap.

The first acceptable sample is returned directly and anchors the output grid. Later outputs are evenly spaced interpolations.

### `reset`

```python
    def reset(self) -> None:
        """Forget resampling state after a confirmed device-session restart."""

        self._source = None
        self._source_id = None
        self._last_received_timestamp_ns = None
        self._previous_sample = None
        self._next_output_timestamp_ns = None
```

Use `reset()` for a confirmed new session. Ordinary quality failures do not reset device identity; they only break interpolation continuity.

Final resampling flow:

```text
VehicleImuSample + VehicleImuQuality
    │
    ├── quality unacceptable
    │       └── clear interpolation continuity; emit nothing
    │
    └── quality acceptable
            │
            ├── first sample: anchor fixed-rate timeline
            └── later sample: interpolate all grid timestamps now bracketed
                    │
                    ▼
            fixed-rate VehicleImuSample sequence
                    │
                    ▼
            causal velocity-model window buffer
```

This completes `resampling.py`. Next we create `windowing.py`, which collects exactly the configured number of resampled samples—50 for the current 5-second, 10 Hz GRU—without crossing a reset boundary.

> yes lets do it, detailed explanations of the functions, and the full file at once, fn snippet then expln then fn snippet and so on

Create [windowing.py](</E:/dead reckoning/src/idr_backend/sensors/windowing.py>) with this complete deterministic window builder.

```python
"""Causal fixed-length windows for the velocity-prediction model.

This module accepts only fixed-rate, quality-gated vehicle-frame IMU samples.
It never creates a window across a resampling reset, timing discontinuity, or
device boundary. It contains no scaler, NumPy, PyTorch, or model inference.
"""

from collections import deque
from dataclasses import dataclass
from math import isfinite

from .types import SensorSource, VehicleImuSample

VELOCITY_MODEL_FEATURE_NAMES = (
    "linear_acceleration_x_mps2",
    "linear_acceleration_y_mps2",
    "linear_acceleration_z_mps2",
    "angular_velocity_x_radps",
    "angular_velocity_y_radps",
    "angular_velocity_z_radps",
)
```

`VELOCITY_MODEL_FEATURE_NAMES` is the final clean six-channel order:

```text
ax, ay, az, gx, gy, gz
```

The model manifest will later store this same order. Do not silently reorder channels.

### `VelocityModelInputWindow`

```python
@dataclass(frozen=True, slots=True)
class VelocityModelInputWindow:
    """One contiguous, fixed-rate sequence ready for model feature scaling."""

    end_timestamp_ns: int
    source: SensorSource
    source_id: str
    sample_period_ns: int
    samples: tuple[VehicleImuSample, ...]

    def __post_init__(self) -> None:
        """Validate that all samples form one chronological model window."""

        if self.sample_period_ns <= 0:
            raise ValueError("sample_period_ns must be positive.")

        if not self.samples:
            raise ValueError("A velocity-model window must contain samples.")

        if self.samples[-1].timestamp_ns != self.end_timestamp_ns:
            raise ValueError(
                "end_timestamp_ns must equal the final sample timestamp."
            )

        previous_timestamp_ns: int | None = None

        for sample in self.samples:
            if (
                sample.source != self.source
                or sample.source_id != self.source_id
            ):
                raise ValueError(
                    "All window samples must belong to the declared device."
                )

            if previous_timestamp_ns is not None:
                if (
                    sample.timestamp_ns - previous_timestamp_ns
                    != self.sample_period_ns
                ):
                    raise ValueError(
                        "Window samples must be exactly fixed-rate and contiguous."
                    )

            previous_timestamp_ns = sample.timestamp_ns
```

This dataclass is the boundary between deterministic preprocessing and the velocity model.

It guarantees:

```text
one device
+ one fixed sample interval
+ chronological contiguous samples
= safe causal model window
```

The end timestamp is the prediction time: a future speed estimate corresponds to the final sample in this window.

### `vehicle_imu_feature_row`

```python
def vehicle_imu_feature_row(
    sample: VehicleImuSample,
) -> tuple[float, float, float, float, float, float]:
    """Extract one clean velocity-model feature row in the fixed six-channel order."""

    values = (
        sample.linear_acceleration_mps2[0],
        sample.linear_acceleration_mps2[1],
        sample.linear_acceleration_mps2[2],
        sample.angular_velocity_radps[0],
        sample.angular_velocity_radps[1],
        sample.angular_velocity_radps[2],
    )

    if not all(isfinite(value) for value in values):
        raise ValueError("Velocity-model features must all be finite.")

    return values
```

This extracts exactly the channels the eventual retrained GRU will consume.

It deliberately excludes:

- Quaternion orientation.
- Calibration confidence.
- Timestamp.
- Source metadata.

Those remain available for quality, uncertainty, and fusion, but are not silently mixed into the velocity feature order.

### `velocity_model_feature_rows`

```python
def velocity_model_feature_rows(
    window: VelocityModelInputWindow,
) -> tuple[tuple[float, float, float, float, float, float], ...]:
    """Extract every sample in a window as ordered model feature rows."""

    return tuple(
        vehicle_imu_feature_row(sample)
        for sample in window.samples
    )
```

This produces a plain Python structure equivalent to:

```text
(window_size, 6)
```

The future velocity adapter will scale these rows, convert them to `float32`, add a batch dimension, and call the GRU or CNN. This module remains deterministic and framework-independent.

### `CausalVehicleImuWindowBuilder.__init__`

```python
class CausalVehicleImuWindowBuilder:
    """Build sliding velocity-model windows from one resampled IMU stream."""

    def __init__(
        self,
        *,
        window_size: int,
        sample_period_ns: int,
    ) -> None:
        """Create a builder with a fixed model-window shape."""

        if window_size <= 0:
            raise ValueError("window_size must be positive.")

        if sample_period_ns <= 0:
            raise ValueError("sample_period_ns must be positive.")

        self._window_size = window_size
        self._sample_period_ns = sample_period_ns

        self._source: SensorSource | None = None
        self._source_id: str | None = None
        self._last_timestamp_ns: int | None = None

        self._samples: deque[VehicleImuSample] = deque(
            maxlen=window_size
        )
```

For the current teammate GRU:

```python
window_size = 50
sample_period_ns = 100_000_000  # 10 Hz
```

These are temporary model settings. Our final trained model manifest decides their real values.

The deque automatically keeps only the newest `window_size` samples, creating a sliding window after warm-up.

### `_register_or_validate_stream`

```python
    def _register_or_validate_stream(
        self,
        sample: VehicleImuSample,
    ) -> None:
        """Bind the window builder to one physical IMU stream."""

        if self._source is None:
            self._source = sample.source
            self._source_id = sample.source_id
            return

        if (
            sample.source != self._source
            or sample.source_id != self._source_id
        ):
            raise ValueError(
                "Cannot mix multiple physical IMU streams in one window builder."
            )
```

One window must never contain samples from different devices. A phone and external IMU need independent resamplers and independent window builders.

### `push`

```python
    def push(
        self,
        sample: VehicleImuSample,
    ) -> VelocityModelInputWindow | None:
        """Accept one resampled sample and emit a complete causal window if ready."""

        self._register_or_validate_stream(sample)

        if self._last_timestamp_ns is not None:
            if sample.timestamp_ns <= self._last_timestamp_ns:
                raise ValueError(
                    "Window-builder timestamps must be strictly increasing."
                )

            if (
                sample.timestamp_ns - self._last_timestamp_ns
                != self._sample_period_ns
            ):
                # A resampling reset or discontinuity occurred. Keep the current
                # sample as the start of a new sequence, never join it to old data.
                self._samples.clear()

        self._samples.append(sample)
        self._last_timestamp_ns = sample.timestamp_ns

        if len(self._samples) < self._window_size:
            return None

        return VelocityModelInputWindow(
            end_timestamp_ns=sample.timestamp_ns,
            source=sample.source,
            source_id=sample.source_id,
            sample_period_ns=self._sample_period_ns,
            samples=tuple(self._samples),
        )
```

`push()` has two possible outcomes:

```text
not enough contiguous samples yet  → None
enough contiguous samples          → VelocityModelInputWindow
```

After the first complete window, every new fixed-rate sample emits another window shifted by one timestep.

That is intentional. Training may use a larger stride to reduce duplicate examples, but runtime inference should update speed at each resampled model timestep.

### `reset`

```python
    def reset(self) -> None:
        """Forget the current device sequence after a confirmed session restart."""

        self._source = None
        self._source_id = None
        self._last_timestamp_ns = None
        self._samples.clear()
```

Use this after a true new session. A quality failure should normally reset the resampler; the resulting timestamp discontinuity automatically clears this window builder.

Final pre-velocity flow:

```text
VehicleImuSample
    │
    ▼ quality.py
VehicleImuQuality
    │
    ▼ resampling.py
fixed-rate VehicleImuSample
    │
    ▼ windowing.py
VelocityModelInputWindow
    │
    ▼ velocity_model_feature_rows()
(window_size, 6) clean feature matrix
    │
    ▼ scale + tensor conversion in future velocity adapter
velocity model prediction
```

This completes the deterministic preprocessing path to the velocity-model boundary.

> now retraining his model? and do i just download the github dataset or what

Not yet a blind retraining run. First we need to replay the dataset through our deterministic pipeline and create a new clean training dataset.

Do **not** download another GitHub copy yet. The teammate project already has the useful raw dataset locally: 40 paired phone/vehicle journeys, about 19.4 hours. Use that as the first reproducible dataset.

The correct order is:

```text
local raw S/V CSV files
    │
    ▼
offline replay adapter
    │
    ▼
our normalization → synchronization → orientation
→ calibration → vehicle rotation → gravity removal
→ quality → resampling → windows
    │
    ▼
clean (window_size, 6) feature windows
+ vehicle-speed labels converted km/h → m/s
    │
    ▼
fit scalers on train journeys only
    │
    ▼
retrain GRU architecture from scratch
```

Two important rules:

- Do not reuse the existing GRU weights: they learned raw phone-frame, gravity-included inputs.
- Do not use the vehicle-speed target to create calibration features. That would leak the answer into model input. Calibration evidence must use deployable information, such as phone GNSS speed/course plus IMU signals.

So our immediate next stage is:

1. Run the deterministic milestone checks we deferred: compilation, imports, and small physics tests.
2. Build an offline CSV replay/data-preparation adapter.
3. Use phone GNSS-derived motion only to generate calibration evidence.
4. Produce cleaned six-channel windows and labels in m/s.
5. Retrain the GRU from the reusable notebook code.
6. Compare cleaned-input GRU against the teammate’s raw-input result on unseen journeys.

If we later need more data, download only the dataset’s original documented release and pin its version in a manifest—don’t mix an unverified GitHub mirror into the existing local set.

The next file should be the offline replay adapter that turns the teammate CSV sequences into our `RawSensorSample` stream.

> okay run the checks yourself, and then explain the methodology and whatever you did here&#x20;
>
> and the data is there in [data](SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/data/) , make an ipynb importing functions from the pipeline, ready to run to retrain, well commented and documented, and eta to run the training, both gru and cnn for comparison

<details><summary>38 previous messages</summary>

> I’ll run the deferred deterministic milestone now: compile every module, import the package, then exercise the physical path from raw acceleration through a clean velocity window. I’ll fix any implementation defects the checks reveal. In parallel, I’ll turn the local CSV dataset into a documented training notebook that imports our pipeline rather than copying its logic.
>
> <details><summary>Explored 2 files, ran 5 commands</summary>
>
> - Ran `& 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m compileall -q src`
>
> - Ran `$env:PYTHONPATH = (Resolve-Path 'src'); & 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "import idr_backend.sensors.types; import idr_backend.sensors.normalization; import idr_backend.sensors.synchronization; import idr_backend.sensors.orientation; import idr_backend.sensors.calibration; import idr_backend.sensors.gravity_removal; import idr_backend.sensors.quality; import idr_backend.sensors.resampling; import idr_backend.sensors.windowing; print('sensor imports passed')"`
>
> - Ran `Get-Content -LiteralPath 'src/idr_backend/sensors/quality.py' -ErrorAction SilentlyContinue`
>
> - Ran `Get-Content -LiteralPath 'src/idr_backend/sensors/windowing.py' -ErrorAction SilentlyContinue`
>
> <details><summary>Explored 2 files</summary>
>
> - Read `./src/idr_backend/sensors/synchronization.py`
> - Read `./pyproject.toml`
>
> </details>
>
> - Ran `Get-Item -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/data/raw/S-M.csv','SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/data/raw/V-M.csv' | Select-Object Name,Length,LastWriteTime | Format-Table -AutoSize`
>
> </details>
>
> Context compaction
>
> Source: automatic
> Status: completed
>
> I’m checking the deterministic path as a connected system now—not just whether Python can import it. I’ll use ideal stationary and known-rotation inputs first, then turn the real dataset into a retraining notebook that calls those pipeline components.
>
> <details><summary>Explored a file, ran 8 commands</summary>
>
> - Ran `Get-Content -LiteralPath 'src/idr_backend/sensors/gravity_removal.py'; Get-Content -LiteralPath 'src/idr_backend/sensors/resampling.py'`
>
> - Ran `Get-ChildItem -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/data/raw' -Filter 'S-*.csv' | Select-Object -First 1 | ForEach-Object { Get-Content -LiteralPath $_.FullName -TotalCount 2 }`
>
> - Ran `& 'E:\Python\python.exe' --version; py -3.11 --version; if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) { nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader } else { 'nvidia-smi unavailable' }`
>
> - Ran `Get-Content -LiteralPath 'src/idr_backend/sensors/types.py' -TotalCount 320; Get-Content -LiteralPath 'src/idr_backend/sensors/quality.py'`
>
> - Ran `Get-ChildItem -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/data/raw' -Filter 'V-*.csv' | Select-Object -First 1 | ForEach-Object { Get-Content -LiteralPath $_.FullName -TotalCount 2 }; Get-Content -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/config.py' -TotalCount 220`
>
> - Ran `@'
> import importlib.util
> for executable in [r'E:\Python\python.exe', r'py -3.11']:
>     print(executable)
> '@ | Out-Null; & 'E:\Python\python.exe' -c "import importlib.util as u; print('torch', bool(u.find_spec('torch'))); print('pandas', bool(u.find_spec('pandas'))); print('sklearn', bool(u.find_spec('sklearn')))"; py -3.11 -c "import importlib.util as u; print('torch', bool(u.find_spec('torch'))); print('pandas', bool(u.find_spec('pandas'))); print('sklearn', bool(u.find_spec('sklearn')))"`
>
> - Ran `Get-Content -LiteralPath 'src/idr_backend/sensors/calibration.py'; Get-Content -LiteralPath 'src/idr_backend/sensors/windowing.py'`
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/sensors/orientation.py`
>
> </details>
>
> - Ran `$env:PYTHONPATH = (Resolve-Path 'src'); @'
> from math import isclose, pi
>
> from idr_backend.sensors.calibration import (
>     CalibrationEvidence, DynamicVehicleCalibrator,
>     derive_sensor_to_vehicle_quaternion, rotate_imu_to_vehicle,
> )
> from idr_backend.sensors.gravity_removal import (
>     derive_vehicle_to_navigation_quaternion, gravity_vector_in_vehicle_frame,
>     remove_gravity_from_vehicle_imu,
> )
> from idr_backend.sensors.normalization import normalize_raw_sample
> from idr_backend.sensors.orientation import (
>     ImuOrientationEstimator, propagate_orientation, rotate_vector,
> )
> from idr_backend.sensors.quality import (
>     VehicleImuQualityLimits, VehicleImuQualityMonitor,
> )
> from idr_backend.sensors.resampling import FixedRateVehicleImuResampler
> from idr_backend.sensors.synchronization import synchronize_pair
> from idr_backend.sensors.types import (
>     CoordinateFrame, MeasurementUnit, OrientationEstimate, RawSensorSample,
>     SensorKind, SensorSource, SynchronizedImuSample, VehicleCalibration,
> )
> from idr_backend.sensors.windowing import (
>     CausalVehicleImuWindowBuilder, velocity_model_feature_rows,
> )
>
> EPS = 1e-9
> def close_vector(left, right):
>     assert all(isclose(a, b, abs_tol=EPS) for a, b in zip(left, right)), (left, right)
>
> # Boundary: units become SI before any geometry/filtering step.
> acc = normalize_raw_sample(RawSensorSample(
>     timestamp_ns=0, source=SensorSource.PHONE, source_id='synthetic-phone',
>     kind=SensorKind.ACCELEROMETER, value=(0.0, 0.0, 1.0),
>     unit=MeasurementUnit.STANDARD_GRAVITY, frame=CoordinateFrame.SENSOR,
> ))
> gyro = normalize_raw_sample(RawSensorSample(
>     timestamp_ns=0, source=SensorSource.PHONE, source_id='synthetic-phone',
>     kind=SensorKind.GYROSCOPE, value=(0.0, 0.0, 180.0),
>     unit=MeasurementUnit.DEGREES_PER_SECOND, frame=CoordinateFrame.SENSOR,
> ))
> assert isclose(acc.value[2], 9.80665, abs_tol=EPS)
> assert isclose(gyro.value[2], pi, abs_tol=EPS)
>
> # Pairing accepts co-timed accel/gyro from exactly one source/frame.
> synchronized = synchronize_pair(acc, gyro, maximum_skew_ns=0)
> assert synchronized.timestamp_ns == 0
>
> # The quaternion convention preserves an identity rotation and correctly
> # integrates a known +Z angular velocity.
> close_vector(rotate_vector((1.0, 0.0, 0.0, 0.0), (1.0, 2.0, 3.0)), (1.0, 2.0, 3.0))
> quarter_turn = propagate_orientation((1.0, 0.0, 0.0, 0.0), (0.0, 0.0, pi / 2), 1.0)
> close_vector(rotate_vector(quarter_turn, (1.0, 0.0, 0.0)), (0.0, 1.0, 0.0))
>
> # Orientation accepts chronological stationary SENSOR-frame observations.
> estimator = ImuOrientationEstimator(
>     accelerometer_correction_gain_per_s=0.5,
>     acceleration_trust_tolerance_mps2=0.5,
> )
> stationary_0 = SynchronizedImuSample(
>     timestamp_ns=0, source=SensorSource.PHONE, source_id='synthetic-phone',
>     frame=CoordinateFrame.SENSOR, acceleration_mps2=(0.0, 0.0, 9.80665),
>     angular_velocity_radps=(0.0, 0.0, 0.0),
>     accelerometer_timestamp_ns=0, gyroscope_timestamp_ns=0,
> )
> stationary_1 = SynchronizedImuSample(
>     timestamp_ns=100_000_000, source=SensorSource.PHONE, source_id='synthetic-phone',
>     frame=CoordinateFrame.SENSOR, acceleration_mps2=(0.0, 0.0, 9.80665),
>     angular_velocity_radps=(0.0, 0.0, 0.0),
>     accelerometer_timestamp_ns=100_000_000, gyroscope_timestamp_ns=100_000_000,
> )
> orientation_0 = estimator.update(stationary_0)
> orientation_1 = estimator.update(stationary_1)
> close_vector(orientation_1.sensor_to_navigation_wxyz[1:], (0.0, 0.0, 0.0))
>
> # Known SENSOR=VEHICLE mounting must derive identity calibration.
> sensor_to_vehicle = derive_sensor_to_vehicle_quaternion((0.0, 0.0, 1.0), (1.0, 0.0, 0.0))
> close_vector(sensor_to_vehicle, (1.0, 0.0, 0.0, 0.0))
> calibration = VehicleCalibration(
>     timestamp_ns=0, source=SensorSource.PHONE, source_id='synthetic-phone',
>     sensor_to_vehicle_wxyz=sensor_to_vehicle, confidence=1.0,
> )
> vehicle_0 = rotate_imu_to_vehicle(stationary_0, calibration, minimum_confidence=0.8)
> assert vehicle_0.frame is CoordinateFrame.VEHICLE_FLU
> close_vector(vehicle_0.acceleration_mps2, (0.0, 0.0, 9.80665))
>
> # ENU gravity is down; for identity VEHICLE->ENU it remains -Z in FLU.
> vehicle_to_navigation = derive_vehicle_to_navigation_quaternion(orientation_0, calibration)
> close_vector(vehicle_to_navigation, (1.0, 0.0, 0.0, 0.0))
> close_vector(gravity_vector_in_vehicle_frame(vehicle_to_navigation), (0.0, 0.0, -9.80665))
> clean_0 = remove_gravity_from_vehicle_imu(vehicle_0, orientation_0, calibration)
> close_vector(clean_0.linear_acceleration_mps2, (0.0, 0.0, 0.0))
>
> # Quality, causal fixed-rate resampling, and windowing retain a contiguous
> # two-sample stationary stream with the expected six feature values.
> quality_monitor = VehicleImuQualityMonitor(VehicleImuQualityLimits(
>     max_gap_ns=250_000_000, max_linear_acceleration_mps2=20.0,
>     max_angular_velocity_radps=10.0, minimum_calibration_confidence=0.8,
> ))
> quality_0 = quality_monitor.assess(clean_0)
> assert quality_0.is_acceptable
> vehicle_1 = rotate_imu_to_vehicle(stationary_1, calibration, minimum_confidence=0.8)
> clean_1 = remove_gravity_from_vehicle_imu(vehicle_1, orientation_1, calibration)
> quality_1 = quality_monitor.assess(clean_1)
> assert quality_1.is_acceptable and quality_1.sample_interval_ns == 100_000_000
> resampler = FixedRateVehicleImuResampler(target_period_ns=100_000_000)
> assert resampler.push(clean_0, quality_0) == (clean_0,)
> assert resampler.push(clean_1, quality_1) == (clean_1,)
> window_builder = CausalVehicleImuWindowBuilder(window_size=2, sample_period_ns=100_000_000)
> assert window_builder.push(clean_0) is None
> window = window_builder.push(clean_1)
> assert window is not None
> assert velocity_model_feature_rows(window) == ((0.0, 0.0, 0.0, 0.0, 0.0, 0.0),) * 2
>
> # Stateful calibration gains a stable solution only after enough coherent evidence.
> calibrator = DynamicVehicleCalibrator(
>     minimum_evidence_count=2, minimum_evidence_confidence=0.8,
>     maximum_disagreement_rad=0.2, remount_evidence_count=2,
> )
> assert calibrator.update(CalibrationEvidence(
>     timestamp_ns=1, source=SensorSource.PHONE, source_id='calibration-phone',
>     vehicle_up_in_sensor=(0.0, 0.0, 1.0), vehicle_forward_in_sensor=(1.0, 0.0, 0.0),
>     confidence=1.0,
> )) is None
> published = calibrator.update(CalibrationEvidence(
>     timestamp_ns=2, source=SensorSource.PHONE, source_id='calibration-phone',
>     vehicle_up_in_sensor=(0.0, 0.0, 1.0), vehicle_forward_in_sensor=(1.0, 0.0, 0.0),
>     confidence=1.0,
> ))
> assert published is not None and isclose(published.confidence, 1.0, abs_tol=EPS)
>
> print('deterministic synthetic checks passed')
> '@ | py -3.11`
>
> </details>
>
> The first behavioral check found an interface mismatch in the test itself: the synchronizer names its limit `max_pair_skew_ns`, not `maximum_skew_ns`. The pipeline code has not failed here; I’m correcting the harness and continuing through the downstream stages.
>
> <details><summary>Ran 2 commands</summary>
>
> - Ran `Get-Content -LiteralPath 'src/idr_backend/sensors/synchronization.py' -TotalCount 100`
> - Ran `$env:PYTHONPATH = (Resolve-Path 'src'); @'
> from math import isclose, pi
> from idr_backend.sensors.calibration import CalibrationEvidence, DynamicVehicleCalibrator, derive_sensor_to_vehicle_quaternion, rotate_imu_to_vehicle
> from idr_backend.sensors.gravity_removal import derive_vehicle_to_navigation_quaternion, gravity_vector_in_vehicle_frame, remove_gravity_from_vehicle_imu
> from idr_backend.sensors.normalization import normalize_raw_sample
> from idr_backend.sensors.orientation import ImuOrientationEstimator, propagate_orientation, rotate_vector
> from idr_backend.sensors.quality import VehicleImuQualityLimits, VehicleImuQualityMonitor
> from idr_backend.sensors.resampling import FixedRateVehicleImuResampler
> from idr_backend.sensors.synchronization import synchronize_pair
> from idr_backend.sensors.types import CoordinateFrame, MeasurementUnit, RawSensorSample, SensorKind, SensorSource, SynchronizedImuSample, VehicleCalibration
> from idr_backend.sensors.windowing import CausalVehicleImuWindowBuilder, velocity_model_feature_rows
> EPS = 1e-9
> def close_vector(left, right):
>     assert all(isclose(a, b, abs_tol=EPS) for a, b in zip(left, right)), (left, right)
> acc = normalize_raw_sample(RawSensorSample(0, SensorSource.PHONE, 'synthetic-phone', SensorKind.ACCELEROMETER, (0.0,0.0,1.0), MeasurementUnit.STANDARD_GRAVITY, CoordinateFrame.SENSOR))
> gyro = normalize_raw_sample(RawSensorSample(0, SensorSource.PHONE, 'synthetic-phone', SensorKind.GYROSCOPE, (0.0,0.0,180.0), MeasurementUnit.DEGREES_PER_SECOND, CoordinateFrame.SENSOR))
> assert isclose(acc.value[2], 9.80665, abs_tol=EPS) and isclose(gyro.value[2], pi, abs_tol=EPS)
> synchronized = synchronize_pair(acc, gyro, max_skew_ns=0); assert synchronized.timestamp_ns == 0
> close_vector(rotate_vector((1.0,0.0,0.0,0.0), (1.0,2.0,3.0)), (1.0,2.0,3.0))
> quarter_turn = propagate_orientation((1.0,0.0,0.0,0.0), (0.0,0.0,pi/2), 1.0); close_vector(rotate_vector(quarter_turn,(1.0,0.0,0.0)),(0.0,1.0,0.0))
> estimator = ImuOrientationEstimator(accelerometer_correction_gain_per_s=0.5, acceleration_trust_tolerance_mps2=0.5)
> stationary_0 = SynchronizedImuSample(0, SensorSource.PHONE, 'synthetic-phone', CoordinateFrame.SENSOR, (0.0,0.0,9.80665), (0.0,0.0,0.0), 0, 0)
> stationary_1 = SynchronizedImuSample(100_000_000, SensorSource.PHONE, 'synthetic-phone', CoordinateFrame.SENSOR, (0.0,0.0,9.80665), (0.0,0.0,0.0), 100_000_000, 100_000_000)
> orientation_0=estimator.update(stationary_0); orientation_1=estimator.update(stationary_1); close_vector(orientation_1.sensor_to_navigation_wxyz[1:],(0.0,0.0,0.0))
> sensor_to_vehicle=derive_sensor_to_vehicle_quaternion((0.0,0.0,1.0),(1.0,0.0,0.0)); close_vector(sensor_to_vehicle,(1.0,0.0,0.0,0.0))
> calibration=VehicleCalibration(0,SensorSource.PHONE,'synthetic-phone',sensor_to_vehicle,1.0)
> vehicle_0=rotate_imu_to_vehicle(stationary_0,calibration,minimum_confidence=0.8); assert vehicle_0.frame is CoordinateFrame.VEHICLE_FLU; close_vector(vehicle_0.acceleration_mps2,(0.0,0.0,9.80665))
> vehicle_to_navigation=derive_vehicle_to_navigation_quaternion(orientation_0,calibration); close_vector(vehicle_to_navigation,(1.0,0.0,0.0,0.0)); close_vector(gravity_vector_in_vehicle_frame(vehicle_to_navigation),(0.0,0.0,-9.80665))
> clean_0=remove_gravity_from_vehicle_imu(vehicle_0,orientation_0,calibration); close_vector(clean_0.linear_acceleration_mps2,(0.0,0.0,0.0))
> quality_monitor=VehicleImuQualityMonitor(VehicleImuQualityLimits(250_000_000,20.0,10.0,0.8)); quality_0=quality_monitor.assess(clean_0); assert quality_0.is_acceptable
> vehicle_1=rotate_imu_to_vehicle(stationary_1,calibration,minimum_confidence=0.8); clean_1=remove_gravity_from_vehicle_imu(vehicle_1,orientation_1,calibration); quality_1=quality_monitor.assess(clean_1); assert quality_1.is_acceptable and quality_1.sample_interval_ns ==100_000_000
> resampler=FixedRateVehicleImuResampler(100_000_000); assert resampler.push(clean_0,quality_0)==(clean_0,); assert resampler.push(clean_1,quality_1)==(clean_1,)
> window_builder=CausalVehicleImuWindowBuilder(window_size=2,sample_period_ns=100_000_000); assert window_builder.push(clean_0) is None; window=window_builder.push(clean_1); assert window is not None; assert velocity_model_feature_rows(window)==((0.0,0.0,0.0,0.0,0.0,0.0),)*2
> calibrator=DynamicVehicleCalibrator(minimum_evidence_count=2,minimum_evidence_confidence=0.8,maximum_disagreement_rad=0.2,remount_evidence_count=2)
> assert calibrator.update(CalibrationEvidence(1,SensorSource.PHONE,'calibration-phone',(0.0,0.0,1.0),(1.0,0.0,0.0),1.0)) is None
> published=calibrator.update(CalibrationEvidence(2,SensorSource.PHONE,'calibration-phone',(0.0,0.0,1.0),(1.0,0.0,0.0),1.0)); assert published is not None and isclose(published.confidence,1.0,abs_tol=EPS)
> print('deterministic synthetic checks passed')
> '@ | py -3.11`
>
> </details>
>
> The connected deterministic smoke test now passes: SI conversion, pairing, quaternion rotation/integration, tilt update, known-mount calibration, gravity cancellation, quality gates, resampling, window construction, and the calibration state transition. I’m using the actual GTX 1650 environment and the paired CSV schema to make the retraining notebook reproducible rather than a source-code copy.
>
> <details><summary>Explored 2 files, ran 5 commands</summary>
>
> - Ran `& 'E:\Python\python.exe' -c "import torch; print(f'torch={torch.__version__} cuda_available={torch.cuda.is_available()}'); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"`
>
> - Ran `& 'E:\Python\python.exe' -c "from pathlib import Path; import pandas as pd; root=Path(r'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/data/raw'); pairs=[]; issues=[]; rows=0; seconds=0.0
> for s in sorted(root.glob('S-*.csv')):
>  v=root/('V-'+s.name[2:]);
>  if not v.exists(): issues.append(f'missing {v.name}'); continue
>  sn=sum(1 for _ in s.open(encoding='utf-8'))-1; vn=sum(1 for _ in v.open(encoding='utf-8'))-1
>  pairs.append(s.stem[2:]); rows += min(sn,vn); seconds += min(sn,vn)/10
>  if sn != vn: issues.append(f'{s.name}: S={sn}, V={vn}')
> print({'pairs':len(pairs),'rows_after_row_alignment':rows,'hours_at_10hz':round(seconds/3600,2),'issues':issues})"`
>
> - Ran `$env:PYTHONPATH = (Resolve-Path 'src'); py -3.11 -m compileall -q src; py -3.11 -c "import tomllib, pathlib; p=tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8')); assert p['build-system']['build-backend']=='hatchling.build'; assert p['project']['requires-python']=='>=3.12, <3.13'; print('compileall + pyproject parse passed')"`
>
> <details><summary>Explored a file</summary>
>
> - Read `./pyproject.toml`
>
> </details>
>
> - Ran `& 'E:\Python\python.exe' -c "from pathlib import Path; root=Path(r'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/data/raw'); pairs=[]; issues=[]; rows=0
> for s in sorted(root.glob('S-*.csv')):
>  v=root/('V-'+s.name[2:]);
>  if not v.exists(): issues.append(f'missing {v.name}'); continue
>  sn=sum(1 for _ in s.open(encoding='cp1252'))-1; vn=sum(1 for _ in v.open(encoding='cp1252'))-1
>  pairs.append(s.stem[2:]); rows += min(sn,vn)
>  if sn != vn: issues.append(f'{s.name}: S={sn}, V={vn}')
> print({'pairs':len(pairs),'rows_after_row_alignment':rows,'hours_at_10hz':round(rows/10/3600,2),'issues':issues})"`
>
> <details><summary>Explored a file</summary>
>
> - Read `./SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/preprocess.py`
>
> </details>
>
> - Ran `rg -n -i "seconds|duration|training|epoch|device|cuda" 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction' -g '*.log' -g '*.txt' -g '*.md' -g '*.json'`
>
> </details>
>
> Stream error
>
> Reconnecting 5/5
> stream disconnected before completion: No such host is known. (os error 11001)
>
> Stream error
>
> Reconnecting... waiting for network
> Connection failed: error sending request
>
> Stream error
>
> Reconnecting... waiting for network
> Connection failed: error sending request
>
> Stream error
>
> Reconnecting... waiting for network
> Connection failed: error sending request
>
> Stream error
>
> Reconnecting... waiting for network
> Connection failed: error sending request
>
> I found one important data correction while preparing this: 3 of the 40 supplied S/V pairs do not have equal row counts, despite the teammate’s documentation claiming they do. The notebook therefore aligns targets by each stream’s relative timestamp with a 75 ms tolerance and reports rejected rows; it never silently truncates or lets a label drift onto the wrong IMU sample.
>
> <details><summary>Created a file, ran 2 commands</summary>
>
> - Wrote `./notebooks/retrain_clean_velocity_models.ipynb` (+581 -0)
> - Ran `& 'E:\Python\python.exe' -c "import json, pathlib; p=pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb'); book=json.loads(p.read_text(encoding='utf-8')); code=[cell['source'] for cell in book['cells'] if cell['cell_type']=='code']; [compile(source, f'{p.name}:cell_{i}', 'exec') for i, source in enumerate(code)]; print(f'notebook JSON + {len(code)} code cells compile passed')"`
> - Ran `$env:PYTHONPATH = (Resolve-Path 'src'); py -3.11 -m compileall -q src; py -3.11 -c "import tomllib, pathlib; p=tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8')); assert p['build-system']['build-backend']=='hatchling.build'; assert p['project']['requires-python']=='>=3.12,<3.13'; print('compileall + pyproject parse passed')"`
>
> </details>
>
> The package compilation and TOML validation pass. The notebook file itself is valid JSON; the first notebook check only needed to account for Jupyter’s permitted “source as a list of lines” representation, so I’m now compiling and executing its setup/preprocessing cells exactly as a kernel would.
>
> <details><summary>Ran 4 commands</summary>
>
> - Ran `& 'E:\Python\python.exe' -c "import json, pathlib; p=pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb'); book=json.loads(p.read_text(encoding='utf-8')); code=[''.join(cell['source']) if isinstance(cell['source'], list) else cell['source'] for cell in book['cells'] if cell['cell_type']=='code']; [compile(source, f'{p.name}:cell_{i}', 'exec') for i, source in enumerate(code)]; namespace={'__name__':'__main__'}; [exec(code[i], namespace) for i in (0,1,2,3)]; print(f'notebook JSON + {len(code)} code cells compile passed; setup and alignment probe executed')"`
> - Ran `& 'E:\Python\python.exe' -c "import json, pathlib, time; p=pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb'); b=json.loads(p.read_text(encoding='utf-8')); c=[''.join(x['source']) if isinstance(x['source'], list) else x['source'] for x in b['cells'] if x['cell_type']=='code']; ns={'__name__':'__main__'}; [exec(c[i], ns) for i in range(6)]; frame=ns['read_aligned_sequence'](*ns['pairs'][0], ns['CONFIG']); start=time.perf_counter(); X,y,audit=ns['replay_clean_sequence'](frame,ns['CONFIG']); print({'sequence':ns['pairs'][0][0], 'X_shape':X.shape, 'target_shape':y.shape, 'audit':audit, 'elapsed_s':round(time.perf_counter()-start,2)})"`
> - Ran `& 'E:\Python\python.exe' -c "import json,pathlib,numpy as np; p=pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb'); b=json.loads(p.read_text()); c=[''.join(x['source']) if isinstance(x['source'],list) else x['source'] for x in b['cells'] if x['cell_type']=='code']; n={'__name__':'__main__'}; [exec(c[i],n) for i in range(4)]; f=n['read_aligned_sequence'](*n['pairs'][0],n['CONFIG']); q=f[f.timestamp_ns<=f.timestamp_ns.iloc[0]+30_000_000_000]; a=q[['acc_x','acc_y','acc_z']].to_numpy(float); g=q[['gyro_x','gyro_y','gyro_z']].to_numpy(float); speed=q.gps_speed_kmh.to_numpy(float)/3.6; t=q.relative_ns.to_numpy(float)*1e-9; d=np.gradient(speed,t); print(n['pairs'][0][0],len(f),len(q),np.nanmin(speed),np.nanmax(speed),np.nanmin(d),np.nanmax(d),np.sum(np.abs(d)>=.2),np.sum(np.abs(d)>=.05),np.sum(np.linalg.norm(g,axis=1)<=1.5),np.sum((np.abs(np.linalg.norm(a,axis=1)-9.80665)<=2)))"`
> - Ran `& 'E:\Python\python.exe' -c "import json,pathlib,numpy as np; p=pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb'); b=json.loads(p.read_text()); c=[''.join(x['source']) if isinstance(x['source'],list) else x['source'] for x in b['cells'] if x['cell_type']=='code']; n={'__name__':'__main__'}; [exec(c[i],n) for i in range(4)]; f=n['read_aligned_sequence'](*n['pairs'][0],n['CONFIG']);
> for secs in (30,60,120,180,300):
>  q=f[f.timestamp_ns<=f.timestamp_ns.iloc[0]+secs*1_000_000_000]; g=q[['gyro_x','gyro_y','gyro_z']].to_numpy(float); s=q.gps_speed_kmh.to_numpy(float)/3.6; t=q.relative_ns.to_numpy(float)*1e-9; d=np.gradient(s,t); useful=(np.abs(d)>=.2)&(np.abs(d)<=6)&(np.linalg.norm(g,axis=1)<=1.5); print(secs,len(q),int(useful.sum()))"`
>
> </details>
>
> The first journey exposed a real calibration-data issue: its first 30 seconds contain only six meaningful GPS-speed changes, so a forward axis would be an invented guess. I’ve kept the safe behavior and am widening the offline calibration prefix to 120 seconds, then dropping it from training. That gives the proxy enough purely sensor/GPS evidence without touching the CAN-bus label.
>
> <details><summary>Edited a file, ran a command</summary>
>
> - Wrote `./notebooks/retrain_clean_velocity_models.ipynb` (+5 -3)
> - Ran `& 'E:\Python\python.exe' -c "import json,pathlib,time; p=pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb'); b=json.loads(p.read_text()); c=[''.join(x['source']) if isinstance(x['source'],list) else x['source'] for x in b['cells'] if x['cell_type']=='code']; [compile(s,f'cell{i}','exec') for i,s in enumerate(c)]; n={'__name__':'__main__'}; [exec(c[i],n) for i in range(6)]; frame=n['read_aligned_sequence'](*n['pairs'][0],n['CONFIG']); start=time.perf_counter(); X,y,audit=n['replay_clean_sequence'](frame,n['CONFIG']); print({'sequence':n['pairs'][0][0], 'X_shape':X.shape, 'target_shape':y.shape, 'audit':audit, 'elapsed_s':round(time.perf_counter()-start,2)})"`
>
> </details>
>
> The first full replay now succeeds on a real 105,950-row journey: 20,909 clean 5-second windows, only 7 quality rejections, and no raw-frame shortcut. I’m running the same preprocessing across all 40 recordings now to verify that the notebook has enough usable journeys for a fair group-disjoint GRU/CNN comparison.
>
> <details><summary>Ran a command</summary>
>
> - Ran `& 'E:\Python\python.exe' -c "import json,pathlib,time; p=pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb'); b=json.loads(p.read_text()); c=[''.join(x['source']) if isinstance(x['source'],list) else x['source'] for x in b['cells'] if x['cell_type']=='code']; n={'__name__':'__main__'}; [exec(c[i],n) for i in range(6)]; start=time.perf_counter(); exec(c[6],n); print({'dataset_shape':n['X'].shape,'usable_journeys':len(set(n['groups'])),'skipped':len(n['skipped']),'elapsed_s':round(time.perf_counter()-start,1)})"`
>
> </details>
>
> The all-recording rehearsal is useful evidence, not a failure to hide: the fixed-prefix proxy only calibrates 4 journeys, which is too few for trustworthy held-out comparison. I’m replacing that notebook-only proxy with a causal rolling-evidence approach that drives the `DynamicVehicleCalibrator` you built. It still uses no CAN-bus labels for calibration, but it lets each journey calibrate once it has actually observed enough past motion.
>
> <details><summary>Edited a file, ran a command</summary>
>
> - Wrote `./notebooks/retrain_clean_velocity_models.ipynb` (+41 -40)
> - Ran `& 'E:\Python\python.exe' -c "import json,pathlib,time; p=pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb'); b=json.loads(p.read_text()); c=[''.join(x['source']) if isinstance(x['source'],list) else x['source'] for x in b['cells'] if x['cell_type']=='code']; [compile(s,f'cell{i}','exec') for i,s in enumerate(c)]; n={'__name__':'__main__'}; [exec(c[i],n) for i in range(6)]; frame=n['read_aligned_sequence'](*n['pairs'][0],n['CONFIG']); start=time.perf_counter(); X,y,audit=n['replay_clean_sequence'](frame,n['CONFIG']); print({'sequence':n['pairs'][0][0], 'X_shape':X.shape, 'audit':audit, 'elapsed_s':round(time.perf_counter()-start,2)})"`
>
> </details>
>
> The rolling method is structurally correct but its evidence threshold was still calibrated for a richer live sensor stream: the first real journey never has 20 independent GPS-speed-change points within any 30-second trailing window. I’m making that dataset-specific threshold explicit at five aggregated points; the calibrator still requires three coherent rolling estimates before accepting a mount.
>
> <details><summary>Edited a file, ran a command</summary>
>
> - Wrote `./notebooks/retrain_clean_velocity_models.ipynb` (+4 -1)
> - Ran `& 'E:\Python\python.exe' -c "import json,pathlib,time; p=pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb'); b=json.loads(p.read_text()); c=[''.join(x['source']) if isinstance(x['source'],list) else x['source'] for x in b['cells'] if x['cell_type']=='code']; [compile(s,f'cell{i}','exec') for i,s in enumerate(c)]; n={'__name__':'__main__'}; [exec(c[i],n) for i in range(6)]; frame=n['read_aligned_sequence'](*n['pairs'][0],n['CONFIG']); start=time.perf_counter(); X,y,audit=n['replay_clean_sequence'](frame,n['CONFIG']); print({'sequence':n['pairs'][0][0], 'X_shape':X.shape, 'audit':audit, 'elapsed_s':round(time.perf_counter()-start,2)})"`
>
> </details>
>
> That replay caught a genuine notebook bug before training: converting nanosecond timestamps to floating point lost sub-microsecond precision, making a calibration appear newer than its own sample. I’m preserving timestamps as `int64` throughout the rolling evidence calculation; this is exactly the kind of strict temporal invariant the pipeline is meant to enforce.
>
> <details><summary>Edited a file, ran 2 commands</summary>
>
> - Wrote `./notebooks/retrain_clean_velocity_models.ipynb` (+7 -3)
> - Ran `& 'E:\Python\python.exe' -c "import json,pathlib,time; p=pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb'); b=json.loads(p.read_text()); c=[''.join(x['source']) if isinstance(x['source'],list) else x['source'] for x in b['cells'] if x['cell_type']=='code']; [compile(s,f'cell{i}','exec') for i,s in enumerate(c)]; n={'__name__':'__main__'}; [exec(c[i],n) for i in range(6)]; frame=n['read_aligned_sequence'](*n['pairs'][0],n['CONFIG']); start=time.perf_counter(); X,y,audit=n['replay_clean_sequence'](frame,n['CONFIG']); print({'sequence':n['pairs'][0][0], 'X_shape':X.shape, 'audit':audit, 'elapsed_s':round(time.perf_counter()-start,2)})"`
> - Ran `& 'E:\Python\python.exe' -c "import json,pathlib,time; p=pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb'); b=json.loads(p.read_text()); c=[''.join(x['source']) if isinstance(x['source'],list) else x['source'] for x in b['cells'] if x['cell_type']=='code']; n={'__name__':'__main__'}; [exec(c[i],n) for i in range(6)]; start=time.perf_counter(); exec(c[6],n); print({'dataset_shape':n['X'].shape,'usable_journeys':len(set(n['groups'])),'skipped':len(n['skipped']),'elapsed_s':round(time.perf_counter()-start,1)})"`
>
> </details>
>
> The timestamp fix is confirmed on the long recording. The causal calibrator is intentionally conservative—it rejects/restarts when fresh evidence conflicts rather than pretending the phone has stayed mounted—so I’m completing the all-journey run to see the usable split before deciding whether the evidence rules need further adjustment.
>
> The causal replay now produces 7,546 usable clean windows across 28 journeys (12 short or never-calibrated recordings are safely skipped), so a journey-disjoint comparison is viable. I’m doing one measured epoch for each model next; that will give a hardware-specific ETA rather than hand-waving from the old raw-input run.
>
> <details><summary>Ran a command</summary>
>
> - Ran `& 'E:\Python\python.exe' -c "import json,pathlib,time; p=pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb'); b=json.loads(p.read_text()); c=[''.join(x['source']) if isinstance(x['source'],list) else x['source'] for x in b['cells'] if x['cell_type']=='code']; n={'__name__':'__main__'}; [exec(c[i],n) for i in range(9)]; torch=n['torch']; nn=n['nn']; DEVICE=n['DEVICE'];
> for name, model in {'gru':n['CleanGruSpeedModel'](), 'cnn':n['CleanCnnSpeedModel']()}.items():
>  model=model.to(DEVICE); optimizer=torch.optim.AdamW(model.parameters(),lr=n['CONFIG'].learning_rate); loss_fn=nn.MSELoss(); start=time.perf_counter(); model.train(); batches=0
>  for features,target in n['train_loader']:
>   optimizer.zero_grad(set_to_none=True); loss=loss_fn(model(features.to(DEVICE)),target.to(DEVICE)); loss.backward(); optimizer.step(); batches+=1
>  if DEVICE.type=='cuda': torch.cuda.synchronize()
>  print({'model':name,'one_epoch_s':round(time.perf_counter()-start,3),'batches':batches,'final_batch_loss':round(float(loss.detach().cpu()),4)})"`
>
> </details>
>
> The measured run is still processing the all-journey deterministic replay before its first GPU epoch—the per-sample geometry is the dominant setup cost, as intended. I’m letting it finish so the ETA includes the real preprocessing cost as well as both neural models.
>
> The GPU measurement is in: after preprocessing, one epoch is ~6.0 s for GRU and ~4.1 s for CNN. It also exposed a split-quality problem: random group splitting placed only 66 windows in test because the journeys are extremely uneven in length. I’m changing the notebook to greedily balance *whole journeys by window count* so validation/test remain genuinely useful.
>
> <details><summary>Edited a file, ran a command</summary>
>
> - Wrote `./notebooks/retrain_clean_velocity_models.ipynb` (+25 -8)
> - Wrote `./notebooks/retrain_clean_velocity_models.ipynb` (+0 -1)
> - Ran `& 'E:\Python\python.exe' -c "import contextlib,io,json,pathlib,time; p=pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb'); b=json.loads(p.read_text()); c=[''.join(x['source']) if isinstance(x['source'],list) else x['source'] for x in b['cells'] if x['cell_type']=='code']; [compile(s,f'cell{i}','exec') for i,s in enumerate(c)]; n={'__name__':'__main__'}; quiet=io.StringIO(); start=time.perf_counter();
> with contextlib.redirect_stdout(quiet):
>  [exec(c[i],n) for i in range(8)]
> exec(c[8],n); print({'notebook_code_cells':len(c),'X_shape':n['X'].shape,'split_windows':{k:len(v) for k,v in n['indices'].items()},'split_journeys':{k:len(set(n['groups'][v])) for k,v in n['indices'].items()},'prep_and_split_s':round(time.perf_counter()-start,1)})"`
>
> </details>
>
> There is no mathematically perfect 70/15/15 journey-disjoint split here: two journeys alone contain most clean windows. I’m making the split policy explicit: seed the three largest journeys into train, validation, and test respectively, then greedily balance the rest. That preserves unseen-journey evaluation and prevents training from being limited to only two recordings.
>
> <details><summary>Edited a file, ran a command</summary>
>
> - Wrote `./notebooks/retrain_clean_velocity_models.ipynb` (+8 -1)
> - Ran `& 'E:\Python\python.exe' -c "import contextlib,io,json,pathlib,time; p=pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb'); b=json.loads(p.read_text()); c=[''.join(x['source']) if isinstance(x['source'],list) else x['source'] for x in b['cells'] if x['cell_type']=='code']; [compile(s,f'cell{i}','exec') for i,s in enumerate(c)]; n={'__name__':'__main__'}; quiet=io.StringIO(); start=time.perf_counter();
> with contextlib.redirect_stdout(quiet):
>  [exec(c[i],n) for i in range(8)]
> exec(c[8],n); print({'notebook_code_cells':len(c),'X_shape':n['X'].shape,'split_windows':{k:len(v) for k,v in n['indices'].items()},'split_journeys':{k:len(set(n['groups'][v])) for k,v in n['indices'].items()},'split_ids':{k:sorted(map(str,set(n['groups'][v]))) for k,v in n['indices'].items()},'prep_and_split_s':round(time.perf_counter()-start,1)})"`
>
> </details>
>
> The revised split is now valid for this uneven dataset: 4,963 train windows from 15 journeys, 1,771 validation windows from the second-largest journey, and 812 test windows from 12 unseen journeys. I’m adding a visible notebook warning about that one-journey validation set, then doing the final file/compilation checks.
>
> <details><summary>Edited a file, ran 3 commands</summary>
>
> - Wrote `./notebooks/retrain_clean_velocity_models.ipynb` (+4 -1)
> - Ran `& 'E:\Python\python.exe' -c "import json, pathlib; p=pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb'); b=json.loads(p.read_text(encoding='utf-8')); code=[''.join(x['source']) if isinstance(x['source'], list) else x['source'] for x in b['cells'] if x['cell_type']=='code']; [compile(source, f'{p.name}:cell_{i}', 'exec') for i,source in enumerate(code)]; print({'valid_json': True, 'code_cells_compiled': len(code), 'total_cells': len(b['cells'])})"`
> - Ran `$env:PYTHONPATH = (Resolve-Path 'src'); py -3.11 -m compileall -q src; py -3.11 -c "import tomllib, pathlib; project=tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8')); assert project['build-system']['build-backend']=='hatchling.build'; assert project['project']['requires-python']=='>=3.12,<3.13'; import idr_backend.sensors.normalization, idr_backend.sensors.synchronization, idr_backend.sensors.orientation, idr_backend.sensors.calibration, idr_backend.sensors.gravity_removal, idr_backend.sensors.quality, idr_backend.sensors.resampling, idr_backend.sensors.windowing; print('package compilation, TOML parsing, and deterministic-module imports passed')"`
> - Ran `Get-Item -LiteralPath 'notebooks/retrain_clean_velocity_models.ipynb' | Select-Object FullName,Length,LastWriteTime; git status --short 2>$null`
>
> </details>
</details>

Created the runnable retraining notebook: [retrain_clean_velocity_models.ipynb](</E:/dead reckoning/notebooks/retrain_clean_velocity_models.ipynb>).

It retrains fresh GRU and CNN models on the six cleaned vehicle-frame IMU features, not the teammate’s raw phone-frame inputs.

Methodology:

1. Read local S/V CSV pairs using CP-1252 encoding.
2. Align vehicle-speed labels to sensor rows by relative timestamp (75 ms tolerance), rather than unsafe row truncation.
3. Normalize and synchronize IMU samples.
4. Estimate orientation, derive causal rolling calibration evidence from IMU + phone GPS-speed changes, and feed it to `DynamicVehicleCalibrator`.
5. Rotate into vehicle FLU, remove gravity, quality-gate, resample to 10 Hz, and form 5-second/50-step windows.
6. Split whole journeys—no overlapping-window leakage—then fit scalers on training journeys only.
7. Train comparable GRU and CNN models and save weights, scalers, manifest, audits, histories, and comparison metrics.

Checks passed:

- Python compilation, package imports, and `pyproject.toml` parsing.
- Synthetic deterministic end-to-end check: units, sync, quaternion rotation, orientation, calibration, gravity removal, quality, resampling, and windowing.
- Notebook JSON and all 12 code cells compile.
- Real replay: 7,546 clean windows from 28 journeys; 12 recordings safely skip because they never produce enough trustworthy calibration evidence.
- Split: 4,963 train windows / 15 journeys; 1,771 validation windows; 812 unseen-test windows / 12 journeys.
- One measured GPU epoch: GRU ≈ 6.0 s, CNN ≈ 4.1 s on the GTX 1650.

ETA for the full notebook: roughly 4–11 minutes including ~50 seconds deterministic preprocessing. The upper end assumes all 50 epochs for both models; early stopping may finish sooner. CUDA startup can add about a minute on a cold environment.

Two important cautions are documented in the notebook: validation is dominated by one large journey because the dataset is highly imbalanced, and the rolling calibration evidence is a transparent training heuristic—not yet a validated production calibration policy.

> whats the cv or hyperparam grid we're using, and add the baseline rf as well + inference time measurement too
> and run it yourself the cells actually, let me know when you do tho

<details><summary>29 previous messages</summary>

> Right now the notebook has **no cross-validation or hyperparameter search**: it uses one journey-disjoint train/validation/test split and fixed GRU/CNN settings. I’ll add an explicit, bounded group-aware tuning protocol, a same-split Random Forest baseline, and measured single-window/batch inference timings for all three—then I’ll execute the full notebook through saved results.
>
> <details><summary>Ran 2 commands</summary>
>
> - Ran `Get-Content -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/train_baseline.py'; Get-Content -LiteralPath 'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/src/train_model.py'`
> - Ran `& 'E:\Python\python.exe' -c "import sklearn; print(sklearn.__version__)"`
>
> </details>
>
> add cv then no we need the best model that we can, better methodology than the teammate as well no keeping him as the kinda base
>
> <details><summary>Ran a command</summary>
>
> - Ran `& 'E:\Python\python.exe' -c "import json,pathlib; b=json.loads(pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb').read_text());
> for i,cell in enumerate(b['cells']):
>  s=''.join(cell.get('source',[])) if isinstance(cell.get('source'),list) else cell.get('source',''); print(i,cell['cell_type'],s.splitlines()[0][:100])"`
>
> </details>
>
> Agreed—the first notebook was a strong pipeline check, but not yet the model-selection methodology I’d want us to defend. I’m upgrading it to: frozen unseen-journey test set, 3-fold journey-aware CV on the remaining data, macro-by-journey selection scoring, a bounded scientifically motivated grid for GRU/CNN/RF, then one final refit and untouched-test comparison.
>
> <details><summary>Edited a file, ran 4 commands</summary>
>
> - Ran `& 'E:\Python\python.exe' -c "import json,pathlib; b=json.loads(pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb').read_text());
> for i in range(12,19):
>  cell=b['cells'][i]; s=''.join(cell['source']) if isinstance(cell['source'],list) else cell['source']; print(f'--- CELL {i} ---'); print(s)"`
> - Ran `rg -n -C 2 "import torch|weight_decay|Comparable models" 'notebooks/retrain_clean_velocity_models.ipynb'`
> - Wrote `./notebooks/retrain_clean_velocity_models.ipynb` (+10 -0)
> - Wrote `./notebooks/retrain_clean_velocity_models.ipynb` (+6 -2)
> - Wrote `./notebooks/retrain_clean_velocity_models.ipynb` (+7 -6)
> - Wrote `./notebooks/retrain_clean_velocity_models.ipynb` (+26 -1)
> - Wrote `./notebooks/retrain_clean_velocity_models.ipynb` (+103 -0)
> - Ran `Get-Content -LiteralPath 'notebooks/retrain_clean_velocity_models.ipynb' | Select-Object -Skip 690 -First 65`
> - Wrote `./notebooks/retrain_clean_velocity_models.ipynb` (+52 -22)
> - Ran `Get-Content -LiteralPath 'notebooks/retrain_clean_velocity_models.ipynb' | Select-Object -Skip 750 -First 52`
> - Wrote `./notebooks/retrain_clean_velocity_models.ipynb` (+2 -2)
> - Wrote `./notebooks/retrain_clean_velocity_models.ipynb` (+50 -10)
> - Wrote `./notebooks/retrain_clean_velocity_models.ipynb` (+4 -2)
>
> </details>
>
> The notebook now contains the stronger protocol: macro-by-journey group CV, frozen final test, a 24-feature RF baseline, and end-to-end post-window inference timing. I’m compiling the changed cells first; if that’s clean, I’ll start the actual full execution and report progress while the CV runs.
>
> <details><summary>Ran 2 commands</summary>
>
> - Ran `& 'E:\Python\python.exe' -c "import json,pathlib; p=pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb'); b=json.loads(p.read_text(encoding='utf-8')); code=[''.join(c['source']) if isinstance(c['source'],list) else c['source'] for c in b['cells'] if c['cell_type']=='code']; [compile(source, f'{p.name}:cell_{i}', 'exec') for i,source in enumerate(code)]; print({'valid_json':True,'code_cells_compiled':len(code),'total_cells':len(b['cells'])})"`
> - Ran `& 'E:\Python\python.exe' -c "import json,pathlib; b=json.loads(pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb').read_text());
> for i,c in enumerate([x for x in b['cells'] if x['cell_type']=='code']):
>  s=''.join(c['source']) if isinstance(c['source'],list) else c['source']; print(i,s.splitlines()[0])"`
>
> </details>
>
> The notebook compiles cleanly. I’m starting the full execution now: deterministic replay, frozen split creation, RF + GRU + CNN CV grids, final refits, inference benchmarks, and artifact saving.
>
> <details><summary>Ran a command</summary>
>
> - Ran `& 'E:\Python\python.exe' -c "import json,pathlib; p=pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb'); b=json.loads(p.read_text(encoding='utf-8')); code=[''.join(c['source']) if isinstance(c['source'],list) else c['source'] for c in b['cells'] if c['cell_type']=='code']; ns={'__name__':'__main__'}; [exec(source, ns) for source in code]; print('FULL_NOTEBOOK_EXECUTION_COMPLETED')"`
>
> </details>
>
> The full run has reached model selection successfully: 6,734 development windows across 16 journeys, with 812 windows from 12 untouched test journeys. The three CV validation folds contain 3,797 / 1,771 / 1,166 windows; macro-by-journey scoring keeps those large recordings from dominating selection.
>
> The data replay and split stages are complete. The run is currently in the RF CV fits; they are CPU-bound and intentionally use 300-tree candidates, so this quiet portion is expected before the neural-grid progress begins.
>
> Still within the RF cross-validation stage. I’m keeping the run going—the first 300-tree fit can be materially slower than later candidates on this machine—but I’ll stop and reduce only the *search cost* if it proves disproportionate; I won’t weaken the held-out evaluation or the pipeline preprocessing.
>
> The RF portion is taking longer than its raw window count suggests, likely because each tree is evaluating the large 3,797-window held fold across all candidates. It is still running rather than stalled; I’m allowing the current measured run to finish so the saved comparison reflects the declared grid.
>
> <details><summary>Ran a command</summary>
>
> - Ran `Get-Process python -ErrorAction SilentlyContinue | Select-Object Id,CPU,WorkingSet64,StartTime,Path | Format-Table -AutoSize`
>
> </details>
>
> I confirmed the execution process is actively consuming CPU and holding the model data, so it is progressing rather than hung; its output is buffered until a stage completes. The RF grid is the slowest part of this first rigorous run.
>
> The run remains active. I’m retaining the full 300-tree RF CV rather than substituting a lighter forest mid-run, because that would make the reported candidate selection inconsistent with the notebook’s declared methodology.
>
> <details><summary>Ran 3 commands</summary>
>
> - Ran `Get-Process -Id 21660 | Select-Object Id,CPU,WorkingSet64,Responding,StartTime | Format-List`
> - Ran `Get-CimInstance Win32_Process -Filter 'ParentProcessId=21660' | Select-Object ProcessId,Name,WorkingSetSize,CommandLine | Format-List; Get-Process | Sort-Object CPU -Descending | Select-Object -First 12 Id,ProcessName,CPU,WorkingSet64 | Format-Table -AutoSize`
> - Ran `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader`
>
> </details>
>
> The RF stage has completed its CPU-heavy work; the process has now moved on without indicating a failure. Its console output is still buffered, so I’ll surface the full selected-model and test results as soon as execution returns.
>
> The process is taking longer than the planned practical budget and has stopped making observable compute progress. I’m ending this stalled execution safely, then I’ll reduce the RF search to a bounded 100-tree CV screening pass and rerun the complete notebook with unbuffered progress so we get a complete, reproducible result rather than an opaque hung job.
>
> <details><summary>Edited a file</summary>
>
> - Wrote `./notebooks/retrain_clean_velocity_models.ipynb` (+8 -8)
> - Wrote `./notebooks/retrain_clean_velocity_models.ipynb` (+1 -1)
>
> </details>
>
> I ended the opaque 300-tree screening run before it produced results. The methodology is unchanged: RF structure is now screened with 100 trees across the same 3 CV folds, then the selected structure is refit with 300 trees for the final comparison. I’m restarting with unbuffered output so every fold is observable.
>
> <details><summary>Ran a command</summary>
>
> - Ran `& 'E:\Python\python.exe' -c "import json,pathlib; p=pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb'); b=json.loads(p.read_text()); code=[''.join(c['source']) if isinstance(c['source'],list) else c['source'] for c in b['cells'] if c['cell_type']=='code']; [compile(s,f'cell{i}','exec') for i,s in enumerate(code)]; print('notebook compile passed')"; & 'E:\Python\python.exe' -u -c "import json,pathlib; p=pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb'); b=json.loads(p.read_text(encoding='utf-8')); code=[''.join(c['source']) if isinstance(c['source'],list) else c['source'] for c in b['cells'] if c['cell_type']=='code']; ns={'__name__':'__main__'}; [exec(source, ns) for source in code]; print('FULL_NOTEBOOK_EXECUTION_COMPLETED')"`
>
> </details>
>
> The restarted execution is progressing normally now. RF CV is producing fold scores: its best candidates are currently around 4.61–5.90 m/s macro journey MAE per fold, which is our honest baseline before seeing any neural result.
>
> Selection is complete. The CNN with channels 32→64→64, dropout 0.20, and learning rate 0.001 wins development CV at **4.655 m/s macro journey MAE**; GRU’s best is **4.932 m/s**, and the best RF is **5.184 m/s**. The notebook is now refitting those selected configurations and measuring their frozen-test accuracy and latency.
>
> The model fits and inference benchmarks have finished. The remaining notebook step is saving the artifact bundle and rendering its chart; the Python execution is currently waiting at that visualization stage, so I’m checking it and will ensure the completed artifacts are present before reporting the result.
>
> <details><summary>Ran a command</summary>
>
> - Ran `Get-ChildItem -LiteralPath 'artifacts/clean_velocity_comparison' -ErrorAction SilentlyContinue | Select-Object Name,Length,LastWriteTime; Get-Process -Id 21660 -ErrorAction SilentlyContinue | Select-Object Id,CPU,Responding | Format-List`
>
> </details>
>
> All output artifacts—including both neural checkpoints, RF baseline, scalers, CV results, held-out predictions, inference CSV, manifest, and chart—were saved successfully. I stopped only the final interactive chart display, which blocks in this non-notebook runner, and I’m making that cell non-blocking for repeat execution.
>
> <details><summary>Edited a file, ran 3 commands</summary>
>
> - Wrote `./notebooks/retrain_clean_velocity_models.ipynb` (+2 -1)
> - Ran `& 'E:\Python\python.exe' -c "import json,pathlib; p=pathlib.Path('notebooks/retrain_clean_velocity_models.ipynb'); b=json.loads(p.read_text(encoding='utf-8')); code=[''.join(c['source']) if isinstance(c['source'],list) else c['source'] for c in b['cells'] if c['cell_type']=='code']; [compile(s,f'cell{i}','exec') for i,s in enumerate(code)]; print({'notebook_json': 'valid', 'compiled_code_cells':len(code)})"`
> - Ran `& 'E:\Python\python.exe' -c "from pathlib import Path; import json,pandas as pd; root=Path('artifacts/clean_velocity_comparison'); print(pd.read_csv(root/'comparison.csv').to_string(index=False)); print('\nCV'); print(pd.read_csv(root/'cv_selection.csv').to_string(index=False)); print('\nLatency'); print(pd.read_csv(root/'inference_latency.csv').to_string(index=False)); manifest=json.loads((root/'manifest.json').read_text()); print('\nSelected:',manifest['selected_parameters'])"`
> - Ran `Get-ChildItem -LiteralPath 'artifacts/clean_velocity_comparison' | Select-Object Name,Length`
>
> </details>
</details>

Implemented and actually ran the upgraded notebook.

The selected model is the CNN:

- CV winner: CNN 32→64→64, dropout 0.20, learning rate 0.001.
- Selection score: 4.655 m/s macro journey MAE.
- Frozen-test macro journey MAE: 4.920 m/s.
- Inference: 0.789 ms per 5-second window on CUDA.

The RF has slightly better window-weighted MAE, but worse macro-by-journey MAE and is ~41× slower per window. We select CNN because the declared selection metric treats each journey fairly.

| Model | CV macro MAE | Test macro MAE | Test MAE | Inference/window |
|---|---:|---:|---:|---:|
| CNN | 4.655 m/s | 4.920 m/s | 3.618 m/s | 0.789 ms |
| Random Forest | 5.184 m/s | 5.168 m/s | 3.563 m/s | 32.276 ms |
| GRU | 4.932 m/s | 5.518 m/s | 4.517 m/s | 1.231 ms |

Methodology now used:

- Test set: 12 complete unseen journeys, frozen before model selection.
- Development set: 16 journeys.
- CV: 3 balanced journey-aware folds.
- Selection metric: macro journey MAE, so huge recordings cannot dominate.
- RF baseline: 24 window statistics—mean/std/min/max × six clean IMU channels.
- RF grid: four depth/leaf-size candidates, screened at 100 trees; chosen structure refit with 300 trees.
- GRU grid: 3 recurrent configurations.
- CNN grid: 3 channel/dropout/learning-rate configurations.
- Latency: 30 warmups plus 200 measured single-window calls; includes scaling, model prediction, and target inverse-scaling, but not deterministic preprocessing.

Updated and rerunnable notebook: [retrain_clean_velocity_models.ipynb](</E:/dead reckoning/notebooks/retrain_clean_velocity_models.ipynb>)

Saved artifacts:

- [comparison.csv](</E:/dead reckoning/artifacts/clean_velocity_comparison/comparison.csv>)
- [cv_selection.csv](</E:/dead reckoning/artifacts/clean_velocity_comparison/cv_selection.csv>)
- [inference_latency.csv](</E:/dead reckoning/artifacts/clean_velocity_comparison/inference_latency.csv>)
- [manifest.json](</E:/dead reckoning/artifacts/clean_velocity_comparison/manifest.json>)
- [CNN checkpoint](</E:/dead reckoning/artifacts/clean_velocity_comparison/cnn_clean_velocity.pt>)
- [Random Forest baseline](</E:/dead reckoning/artifacts/clean_velocity_comparison/random_forest_clean_velocity.joblib>)

One limitation remains explicit: the current causal calibration heuristic yields clean windows from 28 of 40 journeys. That is correct conservative behavior, but improving calibration evidence and collecting more balanced drives is the clearest route to a stronger model.

> how can we decrease the mae, since its like 15 kmph difference which is huge
>
> and even the teammate himself was having 14kmph mae anyway

<details><summary>10 previous messages</summary>

> I’m going to separate “model tuning” from “the problem may be under-observable.” First I’ll inspect which journeys and speed ranges cause the error, because a 13–15 km/h MAE can come from one bad preprocessing/calibration regime, severe dataset imbalance, or from trying to infer absolute speed from IMU alone when the vehicle is moving steadily.
>
> <details><summary>Ran 3 commands</summary>
>
> - Ran `& 'E:\Python\python.exe' -c "import pandas as pd; from pathlib import Path; p=Path(r'artifacts/clean_velocity_comparison/test_predictions.csv'); d=pd.read_csv(p); rows=[]
> for name,g in d.groupby('sequence_id'):
>  a=g.actual_mps; row={'journey':name,'n':len(g),'speed_mean_kmh':a.mean()*3.6,'speed_min_kmh':a.min()*3.6,'speed_max_kmh':a.max()*3.6}
>  for model in ['cnn','gru','random_forest']:
>   pred=g[f'{model}_prediction_mps']; row[f'{model}_mae_kmh']=(a-pred).abs().mean()*3.6; row[f'{model}_bias_kmh']=(pred-a).mean()*3.6
>  rows.append(row)
> out=pd.DataFrame(rows).sort_values('cnn_mae_kmh',ascending=False); print(out.to_string(index=False)); print('\nOverall target quantiles km/h'); print((d.actual_mps.quantile([0,.1,.25,.5,.75,.9,1])*3.6).to_string())"`
> - Ran `& 'E:\Python\python.exe' -c "import pandas as pd; a=pd.read_csv(r'artifacts/clean_velocity_comparison/sequence_audit.csv'); print(a.sort_values('windows',ascending=False).to_string(index=False)); print('\nUsable-window concentration'); print((a.sort_values('windows',ascending=False).assign(share=lambda x:x.windows/x.windows.sum(),cum=lambda x:(x.windows/x.windows.sum()).cumsum()).head(10)[['sequence_id','windows','share','cum']]).to_string(index=False))"`
> - Ran `rg -n "GRU_CANDIDATES|CNN_CANDIDATES|RF_CANDIDATES|macro_journey_mae|window_size|window_stride|gps_speed|target_speed|calibration" 'notebooks/retrain_clean_velocity_models.ipynb'`
>
> </details>
>
> The error is not spread evenly. The CNN is mostly failing on unseen high-speed journeys: about 43–47 km/h error on two ~100 km/h clips and ~32 km/h on Vfa01. Also, 74% of all usable training windows come from only two journeys. I’m checking the intended velocity-adapter contract now, because the largest gain will likely require changing the learning target from absolute speed to an anchored velocity change—not just widening the CNN.
>
> <details><summary>Ran 3 commands</summary>
>
> - Ran `& 'E:\Python\python.exe' -c "import pandas as pd, numpy as np; d=pd.read_csv(r'artifacts/clean_velocity_comparison/test_predictions.csv'); a=d.actual_mps*3.6
> bins=pd.cut(a,[-.001,10,30,50,70,90,110]); rows=[]
> for b,g in d.groupby(bins,observed=True):
>  row={'speed_bin_kmh':str(b),'n':len(g)}
>  for m in ['cnn','gru','random_forest']: row[m+'_mae_kmh']=float(np.mean(np.abs((g.actual_mps-g[m+'_prediction_mps'])*3.6)))
>  rows.append(row)
> print(pd.DataFrame(rows).to_string(index=False))"`
> - Ran `Get-Content -LiteralPath 'src/idr_backend/adapters/velocity_predictor.py'; Get-Content -LiteralPath 'src/idr_backend/pipeline/__init__.py'; rg -n -i "velocity|speed|predictor|anchor|gnss|delta" README.md docs src/idr_backend -g '*.md' -g '*.py'`
> - Ran `& 'E:\Python\python.exe' -c "from pathlib import Path; import pandas as pd, numpy as np; root=Path(r'SIH-2-main/SIH-2-main/IOVNBD-Speed-Prediction/data/raw'); names=['Vta1a','Vta2','M','Vfa02','Vfa01','Vta10','Vta13']; rows=[]
> for n in names:
>  d=pd.read_csv(root/f'V-{n}.csv',encoding='cp1252'); c=[x for x in d.columns if 'Indicated Vehicle Speed' in x][0]; s=pd.to_numeric(d[c],errors='coerce').dropna(); rows.append({'journey':n,'rows':len(s),'mean':s.mean(),'p10':s.quantile(.1),'median':s.median(),'p90':s.quantile(.9),'max':s.max(),'share_above_70':(s>70).mean()})
> print(pd.DataFrame(rows).to_string(index=False))"`
>
> </details>
>
> The pattern is classic regression-to-the-mean: the CNN overpredicts low speeds by roughly 8–14 km/h and underpredicts 90–110 km/h by about 43 km/h. That is exactly what happens when a model is asked for absolute speed from acceleration/gyro alone: at constant 20 km/h and constant 100 km/h, both windows can look nearly identical.
>
> The biggest improvement is therefore architectural: give the predictor a causal speed anchor, then predict change since that anchor (or a correction to inertial integration). Hyperparameter tuning alone will not remove this ambiguity.
>
> User input response
>
> - Can the velocity predictor receive the last trustworthy GNSS forward speed plus elapsed time since that anchor, while current/future GNSS is hidden during simulated outages?
>   - Anchored delta-v (Recommended)
>
> Great—that gives us a solvable formulation. We’ll train on simulated GNSS-blackout episodes: one trustworthy phone-GNSS speed at the start, then only cleaned IMU plus elapsed time; CAN speed remains the label. The model will learn a correction to causal forward-acceleration integration, while the future uncertainty engine can widen covariance as the blackout grows.
>
> User input response
>
> - Which blackout duration should drive model selection and the accuracy target?
>   - all 3, but as u said, <= 5 for 30, 8 for 60, and so on
>
> Plan
>
> # Anchored Residual Velocity Model
>
> ## Summary
>
> Replace absolute-speed-from-IMU prediction with causal anchored dead reckoning:
>
> `last trustworthy GNSS speed + integrated forward acceleration + learned residual correction`
>
> Train and evaluate simulated GNSS outages at 30, 60, and 120 seconds. Retain the teammate’s absolute-speed GRU as an apples-to-apples baseline.
>
> Success targets:
>
> - 0–30 seconds: macro journey MAE ≤ 5 km/h.
> - 30–60 seconds: macro journey MAE ≤ 8 km/h.
> - 60–120 seconds: macro journey MAE ≤ 12 km/h.
> - Report endpoint error, P95 error, bias, and error growth for each horizon.
>
> ## Deterministic Data Improvements
>
> - Make mounting calibration persistent after coherent initialization; noisy acceleration evidence must not repeatedly invalidate a stable mount.
> - Detect remounts separately using sustained gravity/orientation changes rather than individual conflicting acceleration windows.
> - Audit skipped samples by reason: waiting for calibration, low confidence, gap, implausible acceleration, missing label, and incomplete window.
> - Validate S/V time alignment using acceleration-versus-speed-derivative correlation on development journeys only.
> - Aim to recover at least 50,000 quality-controlled training windows across at least 20 journeys.
> - Balance training by journey and speed/outage-duration bins so Vta1a and Vta2 cannot dominate batches.
>
> ## Prediction Formulation
>
> For each simulated blackout:
>
> 1. Reset with the last trustworthy phone-GNSS forward speed.
> 2. Hide all current and future GNSS observations.
> 3. Integrate cleaned FLU forward acceleration causally:
>    `v_integrated = max(0, v_anchor + integral(a_forward dt))`.
> 4. Give the model:
>    - six cleaned IMU channels;
>    - anchor speed;
>    - integrated speed;
>    - elapsed time since anchor;
>    - calibration confidence and deterministic quality indicators.
> 5. Predict a residual correction:
>    `v_predicted = max(0, v_integrated + residual_model_output)`.
>
> Generate balanced blackout episodes ending at 5, 10, 20, 30, 60, 90, and 120 seconds. CAN-bus speed is the label only; current/future GNSS is unavailable to the model.
>
> Compare:
>
> - Constant-speed hold baseline.
> - Pure acceleration integration baseline.
> - Teammate-compatible raw-IMU absolute-speed GRU.
> - Current clean absolute-speed CNN.
> - Random Forest using episode statistics.
> - Anchored residual GRU.
> - Anchored residual causal TCN/CNN.
>
> ## Model Selection
>
> - Reserve a speed-stratified set of whole journeys as the frozen final test set.
> - Use five-fold group CV on development journeys.
> - Select using macro journey MAE averaged across blackout-duration bins.
> - Use Huber loss in physical m/s units and journey-balanced sampling.
>
> Bounded neural search:
>
> - Residual GRU candidates:
>   - 32 hidden, 1 layer, dropout 0.10, LR 0.001.
>   - 64 hidden, 1 layer, dropout 0.10, LR 0.0005.
>   - 64 hidden, 2 layers, dropout 0.20, LR 0.001.
>   - 96 hidden, 2 layers, dropout 0.20, LR 0.0005.
> - Residual causal TCN candidates:
>   - 32 channels, dropout 0.10, LR 0.001.
>   - 64 channels, dropout 0.10, LR 0.0005.
>   - 64 channels, dropout 0.20, LR 0.0005.
> - Use 12-epoch/three-fold screening, then evaluate the top two candidates per family with full five-fold CV and 40 epochs.
> - Refit the selected configuration on all development journeys using the median best epoch from CV.
> - Open the frozen test set exactly once.
>
> ## Outputs and Tests
>
> - Save model weights, feature/target transforms, anchor contract, selected parameters, CV results, per-horizon metrics, per-journey metrics, and test predictions.
> - Measure:
>   - per-sample stateful inference;
>   - complete 30/60/120-second replay latency;
>   - CPU and CUDA latency;
>   - memory usage.
> - Verify:
>   - no current/future GNSS leakage;
>   - no windows cross journey or remount boundaries;
>   - anchor resets clear recurrent state;
>   - speed remains nonnegative;
>   - every scaler is fit only on development-fold data;
>   - test journeys are never referenced during calibration tuning, model selection, or epoch selection.
>
> The uncertainty engine remains downstream. It will later consume predicted speed, blackout duration, calibration quality, IMU quality, and residual-model metadata to increase covariance as the anchor ages.
>
> Plan implementation
>
> Status: running
> # Anchored Residual Velocity Model
>
> ## Summary
>
> Replace absolute-speed-from-IMU prediction with causal anchored dead reckoning:
>
> `last trustworthy GNSS speed + integrated forward acceleration + learned residual correction`
>
> Train and evaluate simulated GNSS outages at 30, 60, and 120 seconds. Retain the teammate’s absolute-speed GRU as an apples-to-apples baseline.
>
> Success targets:
>
> - 0–30 seconds: macro journey MAE ≤ 5 km/h.
> - 30–60 seconds: macro journey MAE ≤ 8 km/h.
> - 60–120 seconds: macro journey MAE ≤ 12 km/h.
> - Report endpoint error, P95 error, bias, and error growth for each horizon.
>
> ## Deterministic Data Improvements
>
> - Make mounting calibration persistent after coherent initialization; noisy acceleration evidence must not repeatedly invalidate a stable mount.
> - Detect remounts separately using sustained gravity/orientation changes rather than individual conflicting acceleration windows.
> - Audit skipped samples by reason: waiting for calibration, low confidence, gap, implausible acceleration, missing label, and incomplete window.
> - Validate S/V time alignment using acceleration-versus-speed-derivative correlation on development journeys only.
> - Aim to recover at least 50,000 quality-controlled training windows across at least 20 journeys.
> - Balance training by journey and speed/outage-duration bins so Vta1a and Vta2 cannot dominate batches.
>
> ## Prediction Formulation
>
> For each simulated blackout:
>
> 1. Reset with the last trustworthy phone-GNSS forward speed.
> 2. Hide all current and future GNSS observations.
> 3. Integrate cleaned FLU forward acceleration causally:
>    `v_integrated = max(0, v_anchor + integral(a_forward dt))`.
> 4. Give the model:
>    - six cleaned IMU channels;
>    - anchor speed;
>    - integrated speed;
>    - elapsed time since anchor;
>    - calibration confidence and deterministic quality indicators.
> 5. Predict a residual correction:
>    `v_predicted = max(0, v_integrated + residual_model_output)`.
>
> Generate balanced blackout episodes ending at 5, 10, 20, 30, 60, 90, and 120 seconds. CAN-bus speed is the label only; current/future GNSS is unavailable to the model.
>
> Compare:
>
> - Constant-speed hold baseline.
> - Pure acceleration integration baseline.
> - Teammate-compatible raw-IMU absolute-speed GRU.
> - Current clean absolute-speed CNN.
> - Random Forest using episode statistics.
> - Anchored residual GRU.
> - Anchored residual causal TCN/CNN.
>
> ## Model Selection
>
> - Reserve a speed-stratified set of whole journeys as the frozen final test set.
> - Use five-fold group CV on development journeys.
> - Select using macro journey MAE averaged across blackout-duration bins.
> - Use Huber loss in physical m/s units and journey-balanced sampling.
>
> Bounded neural search:
>
> - Residual GRU candidates:
>   - 32 hidden, 1 layer, dropout 0.10, LR 0.001.
>   - 64 hidden, 1 layer, dropout 0.10, LR 0.0005.
>   - 64 hidden, 2 layers, dropout 0.20, LR 0.001.
>   - 96 hidden, 2 layers, dropout 0.20, LR 0.0005.
> - Residual causal TCN candidates:
>   - 32 channels, dropout 0.10, LR 0.001.
>   - 64 channels, dropout 0.10, LR 0.0005.
>   - 64 channels, dropout 0.20, LR 0.0005.
> - Use 12-epoch/three-fold screening, then evaluate the top two candidates per family with full five-fold CV and 40 epochs.
> - Refit the selected configuration on all development journeys using the median best epoch from CV.
> - Open the frozen test set exactly once.
>
> ## Outputs and Tests
>
> - Save model weights, feature/target transforms, anchor contract, selected parameters, CV results, per-horizon metrics, per-journey metrics, and test predictions.
> - Measure:
>   - per-sample stateful inference;
>   - complete 30/60/120-second replay latency;
>   - CPU and CUDA latency;
>   - memory usage.
> - Verify:
>   - no current/future GNSS leakage;
>   - no windows cross journey or remount boundaries;
>   - anchor resets clear recurrent state;
>   - speed remains nonnegative;
>   - every scaler is fit only on development-fold data;
>   - test journeys are never referenced during calibration tuning, model selection, or epoch selection.
>
> The uncertainty engine remains downstream. It will later consume predicted speed, blackout duration, calibration quality, IMU quality, and residual-model metadata to increase covariance as the anchor ages.
</details>

The main problem is not the CNN size—it is the target formulation. Absolute speed is not observable from IMU alone during steady motion. A stationary-looking five-second window can represent 20 km/h or 100 km/h, so every model regresses toward the dataset mean. That explains the current pattern:

- Low speeds are overestimated by roughly 8–14 km/h.
- 90–110 km/h samples are underestimated by roughly 43 km/h.
- 74% of usable windows come from only two journeys.
- Only 7,546 clean windows survive from roughly 693,000 source rows.
