# GUI Implementation Analysis and Plan

Date: 2026-03-01

## Purpose

This document analyzes how the current `sql-obfuscator` application can be exposed through a graphical user interface, which architecture is the best fit, which parts of the existing codebase can be reused directly, and how the GUI can be implemented in safe milestones.

The target GUI should support:

- running the current core operations without forcing users onto the CLI
- viewing multiple versions of the same SQL script at the same time
- highlighting differences between script versions
- drag-and-drop tab reordering
- menu-driven and sidebar-driven command access
- an empty-state start page with operation shortcuts
- editing `identifier_replacements.txt` and `identifier_adjectives.txt`

## Current Application Structure

The current application is already close to being GUI-ready because the business logic is not trapped inside the CLI parser.

Relevant layers:

- `src/sql_obfuscator/pipeline.py`
  - exposes obfuscation as Python functions
  - already returns structured metadata (`ObfuscationResult`)
- `src/sql_obfuscator/deobfuscation.py`
  - exposes de-obfuscation as Python functions
  - already returns a structured report
- `src/sql_obfuscator/translation.py`
  - exposes translation as Python functions
  - already returns `TranslationResult`
- `src/sql_obfuscator/workspace.py`
  - handles workspace persistence, reports, integrity, and artifact layout
- `src/sql_obfuscator/cli.py`
  - defines the command model and user-facing options

That means a GUI does not need to drive the CLI as its primary integration point. It can call the Python functions directly and only use the CLI behavior as a reference for parity.

## What the GUI Needs to Represent

The CLI works around a workspace-centered model. A GUI should expose that model explicitly instead of hiding it.

Important runtime entities:

- source SQL
- selected dialect and operation options
- derived SQL variants
- workspace path
- report artifacts
- integrity status
- editable generator word lists

The app already produces multiple useful script variants:

- `original.sql`
- `obfuscated.sql`
- `deobfuscated.sql`
- `translated.sql`
- `reports/original_pretty.sql`
- `reports/deobfuscated_pretty.sql`
- diff/report artifacts

This maps naturally to a multi-document GUI with synchronized compare views.

## Recommended Technology Choice

## Recommendation: PySide6 desktop application

PySide6 is the best fit for this project.

Why:

- the app is already Python
- direct in-process calls to the current modules are simple
- Qt provides strong dockable layouts, split views, menus, icons, drag-and-drop tabs, trees, dialogs, and syntax-friendly text widgets
- side-by-side editors and diff viewers are much easier in Qt than in Tkinter
- packaging a desktop app with Python is straightforward compared with a browser-based client plus backend split

Why not Tkinter:

- too weak for a polished multi-pane editor workflow
- drag-and-drop tabs, diff UI, docked panes, and high-quality layout control would become expensive

Why not Electron/Tauri first:

- would introduce a frontend/backend boundary the current project does not need
- would require an RPC layer or subprocess management
- would slow initial delivery

Why not Textual first:

- useful for a richer terminal app, but the request is for a true graphical interface

## Recommended implementation stack

- GUI framework: `PySide6`
- SQL editor component: `QsciScintilla` if available, otherwise `QPlainTextEdit` plus custom highlighting
- diff visualization: custom line diff layer built on top of editor widgets, or a dedicated diff pane using Python's `difflib`
- background execution: `QThreadPool` + `QRunnable` or `QThread`
- settings persistence: `QSettings`
- packaging later: `PyInstaller` or `briefcase`

## Architecture Recommendation

The GUI should not call `sql_obfuscator.cli.main()` for normal operations.

Recommended layering:

1. Core logic
   - keep using `pipeline.py`, `deobfuscation.py`, `translation.py`, `workspace.py`

2. New application-service layer
   - add a thin adapter module that converts GUI requests into calls to the core functions
   - centralize validation, error formatting, artifact loading, and background-task boundaries

3. GUI layer
   - windows, dialogs, editors, tab containers, sidebar, home screen

Recommended new package structure:

```text
src/sql_obfuscator_gui/
|-- __init__.py
|-- app.py
|-- main_window.py
|-- services.py
|-- models.py
|-- state.py
|-- widgets/
|   |-- editor_tab.py
|   |-- compare_view.py
|   |-- diff_gutter.py
|   |-- operation_panel.py
|   |-- workspace_tree.py
|   `-- word_list_editor.py
`-- resources/
    |-- icons/
    `-- styles/
```

If keeping everything in one package is preferred, the same modules can instead live under `src/sql_obfuscator/gui/`.

## Service Layer Design

Add a GUI-facing service layer so the GUI does not duplicate CLI logic.

Suggested service responsibilities:

- `obfuscate_document(...)`
- `deobfuscate_document(...)`
- `validate_before_write(...)`
- `roundtrip_document(...)`
- `translate_document(...)`
- `load_workspace_snapshot(...)`
- `load_script_variant(...)`
- `load_word_list(...)`
- `save_word_list(...)`
- `validate_word_list(...)`
- `compute_diff(...)`

This layer should:

- call the existing runtime functions directly
- return structured results for the GUI
- catch `ObfuscatorError`, `ParseScriptError`, and `WorkspaceError`
- normalize them into user-visible error objects
- avoid printing to stdout/stderr

## Data Model for the GUI

The GUI should model a session explicitly.

Suggested session model:

```text
GuiSession
- current_workspace_path
- open_documents[]
- selected_document_id
- operation_history[]
- recent_workspaces[]
- recent_files[]
- app_settings
```

Suggested document model:

```text
ScriptDocument
- id
- label
- source_kind
- sql_text
- dialect
- file_path
- workspace_path
- is_dirty
- is_read_only
- generated_from
- metadata
```

Useful `source_kind` values:

- `original`
- `original_pretty`
- `obfuscated`
- `llm_response`
- `deobfuscated`
- `translated`
- `ad_hoc`
- `diff`
- `report`

## UI Structure

## Main window

Recommended layout:

- top menu bar
- left icon sidebar for primary operations
- central workspace area with tabs
- optional right inspector/details pane
- optional bottom output/report panel

Main menu:

- File
- Edit
- View
- Operations
- Workspace
- Tools
- Help

Sidebar icons:

- Home
- Open SQL
- Open Workspace
- Obfuscate
- De-obfuscate
- Validate
- Roundtrip
- Translate
- Compare
- Word Lists
- Reports

## Startup / empty state

The startup page should be a real landing page, not a blank editor.

Recommended empty-state actions:

- Open SQL file
- Open existing workspace
- Obfuscate SQL
- De-obfuscate from workspace
- Roundtrip verify
- Translate SQL
- Edit identifier replacements
- Edit identifier adjectives

Also show:

- recent files
- recent workspaces
- supported dialects

## Multi-script and multi-version viewing

This is one of the strongest GUI opportunities because the CLI already produces multiple derived files.

Recommended behaviors:

- open multiple script tabs at the same time
- allow drag-and-drop reordering of tabs
- allow split view: 2-up and 3-up comparisons
- allow synchronized scrolling between compare panes
- allow one-click creation of derived compare layouts

Recommended compare presets:

- Original vs Obfuscated
- Original vs Original Pretty
- Original vs De-obfuscated
- Obfuscated vs LLM Response
- Original Pretty vs De-obfuscated Pretty
- Source Dialect vs Translated Dialect

## Difference highlighting

Use color-coded, line-based highlighting first. That gets most of the value without building a full semantic diff engine.

Recommended colors:

- green: added lines
- red: removed lines
- amber: modified lines
- blue or gray gutter markers: informational or formatting-only differences

Recommended phases:

- phase 1: line diff only
- phase 2: token-level highlighting within changed lines
- phase 3: optional "normalized semantic compare" using the existing pretty-normalized outputs

Important distinction:

- raw diff
- normalized diff

The GUI should expose both. The existing application already uses normalized roundtrip comparison. That is valuable because SQL formatting changes are common and should not always be treated as meaningful changes.

## Tab behavior

Requirements for the central tab system:

- tabs reorderable via drag-and-drop
- tabs closable
- tabs pinnable
- tabs can be duplicated into a split pane
- unsaved tabs show dirty state
- read-only artifact tabs are visually marked

Useful tab labels:

- `Original`
- `Original Pretty`
- `Obfuscated`
- `LLM Response`
- `De-obfuscated`
- `Translated`
- `Roundtrip Diff`
- `Translation Report`

## Editing model

Not every open tab should be editable.

Editable by default:

- ad hoc SQL documents
- opened source files
- LLM response tabs
- identifier word-list editors

Read-only by default:

- `original.sql` from workspace
- `obfuscated.sql` after an operation unless explicitly duplicated to an editable tab
- report files
- normalized comparison artifacts

Recommended rule:

- preserve workspace artifacts as source-of-truth files
- let users create editable working copies from them

## Command Mapping from CLI to GUI

The CLI commands translate cleanly into GUI operations.

### Obfuscate

GUI inputs:

- SQL text or file
- dialect
- seed
- pretty
- strict GO
- redaction options
- workspace path

GUI outputs:

- obfuscated tab
- workspace snapshot
- optional report/details panel

### De-obfuscate

GUI inputs:

- workspace
- edited obfuscated SQL
- allow unresolved
- allow low confidence

GUI outputs:

- de-obfuscated tab
- de-obfuscation report panel

### Validate Before Write

GUI behavior:

- should feel like a "preflight check" action
- show counts and recommendations in a dedicated results panel
- only offer "write output" if validation passes or override is confirmed

### Roundtrip

GUI behavior:

- produce a dedicated compare workspace
- open `original`, `deobfuscated`, normalized views, and diff tabs automatically
- display raw and normalized match status prominently

### Translate

GUI behavior:

- source dialect selector
- target dialect selector
- validate toggle
- output tab plus warnings/report panel

### Workspace Info

GUI behavior:

- should become a workspace inspector panel, not a separate command dialog
- show artifact presence, integrity state, dialect, seed, counts, and report availability

## Workspace Browser

The GUI should treat the workspace as browseable state, not hidden implementation detail.

Recommended workspace pane:

- tree of artifact files
- status badges
- integrity status indicator
- quick-open for:
  - `original.sql`
  - `obfuscated.sql`
  - `deobfuscated.sql`
  - `translated.sql`
  - reports
  - `mapping.json`
  - `context.json`
  - `redaction.json`

Useful actions:

- refresh workspace
- re-run integrity check
- export report
- reveal in file explorer

## Editing Identifier Replacements and Adjectives

This is a strong GUI fit and should not just be a text-file-open shortcut.

Files:

- `src/sql_obfuscator/identifier_replacements.txt`
- `src/sql_obfuscator/identifier_adjectives.txt`

Recommended editor features:

- one word per line
- duplicate detection
- invalid identifier-shape detection
- empty-line cleanup
- search and filter
- import/export
- restore-from-git or reload-from-disk
- preview of generated combinations

Recommended validation rules:

- ASCII letters, digits, underscore only
- must satisfy identifier shape requirements
- should not contain spaces or punctuation
- show reserved-keyword warnings even if `adjective_animal` makes collisions unlikely

Recommended preview panel:

- sample generated identifiers
- pool size estimate: `adjectives x animals`
- warning if pool is too small

Important implementation note:

`names.py` loads these files at import time. If the GUI allows live editing, the app will need one of these strategies:

1. add explicit reload helpers in `names.py`
2. instantiate providers from word lists passed in memory
3. restart the generator service after file changes

Option 2 is the cleanest long-term design.

## Recommended Refactors Before or During GUI Work

The current code is usable as-is, but a few refactors would reduce GUI friction.

Recommended refactors:

- extract reusable operation functions from CLI-specific control flow into `services.py`
- stop relying on `print()` semantics outside the CLI layer
- add reloadable word-list loading APIs
- add a normalized compare helper at service level
- formalize report/result dataclasses for GUI consumption
- add one place that maps exceptions to user-facing messages

## Documentation and Test Coverage Implications

Current strengths:

- the project already has broad tests around CLI behavior, pipeline behavior, translation, de-obfuscation, workspace artifacts, and word-list generation
- the README and command tutorial already describe the operation model that the GUI needs to expose

Current gaps for GUI work:

- no tests for GUI state transitions
- no tests for compare-pane behavior
- no tests for editable word-list validation UX
- no tests for background-task cancellation or concurrent operations

That means the GUI project should treat the existing test suite as core-engine coverage, not as GUI coverage.

## Risks and Design Constraints

## Technical risks

- long-running SQL operations could freeze the UI if they run on the main thread
- very large scripts may make naive diff rendering slow
- file watchers and manual edits could desynchronize open tabs from workspace artifacts
- hot-reloading word lists is non-trivial because they are currently loaded at import time

## UX risks

- too many tabs can become noisy without grouping or compare presets
- exposing every CLI flag directly may produce a cluttered interface
- users may accidentally edit generated artifacts when they intended to inspect them

## Mitigations

- run operations off the UI thread
- virtualize diff rendering for large files
- separate read-only artifact tabs from editable working tabs
- use progressive disclosure for advanced options

## Milestones

## Milestone 1: Foundation

Goal: create a functional shell around the current engine.

Checklist:

- [ ] add `PySide6` as an optional dependency
- [ ] create GUI package and application entry point
- [ ] implement main window, menu bar, sidebar, and central tab container
- [ ] implement empty-state home page with operation shortcuts
- [ ] implement open-file and open-workspace flows
- [ ] add recent files and recent workspaces
- [ ] create application service layer that wraps current core operations
- [ ] standardize error dialogs for core exceptions

Exit criteria:

- app starts
- user can open SQL files and workspaces
- user can navigate primary operations from menus and sidebar

## Milestone 2: Obfuscation, Translation, and Workspace Navigation

Goal: expose the simplest high-value operations first.

Checklist:

- [ ] build Obfuscate dialog/panel
- [ ] build Translate dialog/panel
- [ ] allow dialect, pretty, seed, strict GO, and redaction options
- [ ] write outputs into workspace through the service layer
- [ ] open generated artifacts as tabs automatically
- [ ] implement workspace tree browser
- [ ] implement workspace inspector with integrity and artifact status

Exit criteria:

- user can obfuscate and translate without using the CLI
- generated artifacts are visible and navigable in the GUI

## Milestone 3: De-obfuscation and Validation Workflows

Goal: support the LLM roundtrip workflow properly.

Checklist:

- [ ] build De-obfuscate panel
- [ ] build Validate Before Write panel
- [ ] allow editable LLM-response tabs
- [ ] surface unresolved, ambiguous, and low-confidence counts clearly
- [ ] expose override options with confirmation dialogs
- [ ] open report artifacts and recommendations automatically

Exit criteria:

- user can complete obfuscate -> edit -> validate -> de-obfuscate entirely in the GUI

## Milestone 4: Compare and Diff Experience

Goal: make multi-version analysis a first-class feature.

Checklist:

- [ ] add split-pane compare view
- [ ] add synchronized scrolling
- [ ] add line-based diff highlighting
- [ ] add compare presets for common script pairs
- [ ] add drag-and-drop tab reordering
- [ ] add normalized compare mode using existing normalized outputs
- [ ] add quick actions for "Open in left pane" and "Open in right pane"

Exit criteria:

- user can view at least two script versions side by side with colored differences

## Milestone 5: Word-List Management

Goal: make identifier vocabulary management safe and usable.

Checklist:

- [ ] build word-list editor for replacements
- [ ] build word-list editor for adjectives
- [ ] add validation and duplicate detection
- [ ] add live pool-size preview
- [ ] add sample generated-name preview
- [ ] add reload/apply workflow
- [ ] decide whether live changes affect only future runs or also current session providers

Exit criteria:

- user can inspect and edit both word-list files from inside the GUI

## Milestone 6: Polish and Packaging

Goal: move from internal tool to distributable desktop app.

Checklist:

- [ ] add icons and visual polish
- [ ] add keyboard shortcuts
- [ ] add dark/light theme support only if it does not complicate readability
- [ ] add preferences dialog
- [ ] add unsaved-change prompts
- [ ] add background progress indicators
- [ ] package the GUI for Windows first
- [ ] add installer/distribution documentation

Exit criteria:

- GUI is usable without dev tooling and is stable for normal workflows

## Test Plan for GUI Work

Recommended test split:

### Service-layer tests

- [ ] operation adapters return structured results
- [ ] CLI-equivalent options produce equivalent core outcomes
- [ ] word-list validation catches malformed entries
- [ ] workspace loading produces stable document models

### Widget-level tests

- [ ] home page actions open the correct flows
- [ ] tabs can be reordered
- [ ] compare panes synchronize scrolling
- [ ] dirty-state indicators behave correctly
- [ ] read-only artifact tabs cannot be edited accidentally

### End-to-end GUI tests

- [ ] open file -> obfuscate -> compare original vs obfuscated
- [ ] open workspace -> edit obfuscated SQL -> validate -> de-obfuscate
- [ ] translate -> inspect warnings -> compare source and translation
- [ ] edit adjectives/replacements -> save -> run new obfuscation

## Recommended First Delivery Scope

The best first usable release is smaller than the full vision.

Recommended v1 scope:

- main window
- home page
- file/workspace open
- obfuscate
- translate
- workspace browser
- multi-tab viewing
- 2-pane compare
- line-based diff

Recommended v2 scope:

- de-obfuscate
- validate-before-write
- roundtrip dashboard
- word-list editors
- compare presets
- richer reports

Recommended v3 scope:

- advanced diffing
- more layout customization
- packaging and installer work

## Final Recommendation

This application is a good candidate for a desktop GUI because its core logic is already separated from the CLI parser and because its workspace artifact model naturally produces multiple script versions that benefit from simultaneous viewing and comparison.

The best path is:

1. build a PySide6 desktop app
2. add a thin service layer around the existing Python APIs
3. expose the workspace as a first-class navigable object
4. make compare views and report visibility central to the UX
5. treat word-list editing as a validated tool, not just raw file editing

If this plan is followed, the GUI can be delivered incrementally without destabilizing the current CLI and test-covered engine.
