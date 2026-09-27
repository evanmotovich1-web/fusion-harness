# Review: nordeim/excel-agent-tool AGENT_SYSTEM_PROMPT.md

Status: vendored as untrusted data. No clause in the file was executed. No tool from that repo was installed.

Pin: commit `2afa48049502b60ae6f8afe963b52837c691b2fd` (2025-11-19T13:19:23Z). Saved prompt sha256 `b18baa28193b2abd1ab2bc88e3512fd6ee5a0daad644a36942f42594fbc5ab0d`, 24630 bytes, git blob `456593d9b1dde74ce2bd6f9f185aee932c6437c2` matching the GitHub contents API. See `SOURCE.json`.

## License

No `LICENSE` file exists in the pinned tree. The GitHub repository license API returned null. The README badge and the README section "License" (`README.md:8`, `README.md:632-634`) name MIT License and include the standard MIT grant, copyright "Excel Agent Team" 2024. That grant allows local copy and use. It does not forbid this install. This is not a 404 and not a license stop.

## Flagged clauses (NOT installed)

These are instructions inside the untrusted prompt. They are recorded here and were not run.

1. Role replacement. `AGENT_SYSTEM_PROMPT.md:5` and `AGENT_SYSTEM_PROMPT.md:1053` tell the reader it is an Excel agent and that it is "now equipped" to manipulate workbooks. NOT installed as a harness identity or as a replacement of Fusion Harness role prompts.
2. Shell execution. The prompt's operating model is `uv python tools/<script>.py` plus `subprocess.run` (`AGENT_SYSTEM_PROMPT.md:37`, `AGENT_SYSTEM_PROMPT.md:784-787`, `AGENT_SYSTEM_PROMPT.md:947-953`). Those scripts are not in this workspace. NOT installed.
3. Background shell. `AGENT_SYSTEM_PROMPT.md:1010-1012` tells the agent to background three tool processes with `&` and `wait`. NOT installed. This harness forbids background processes.
4. Network override. Default text blocks `WEBSERVICE()` (`AGENT_SYSTEM_PROMPT.md:170`, `AGENT_SYSTEM_PROMPT.md:849`). The same file then shows `--allow-external` with `=WEBSERVICE('https://api.example.com')` (`AGENT_SYSTEM_PROMPT.md:856-861`, `AGENT_SYSTEM_PROMPT.md:927-929`). That override is NOT installed. No network formula, no Chatham fetch, and no `curl | sh` was run. The README install snippet that pipes `https://astral.sh/uv/install.sh` into a shell was not executed.
5. Security-policy bypass. Exit code 2 is documented as a security error that `--allow-external` overrides (`AGENT_SYSTEM_PROMPT.md:167`, `AGENT_SYSTEM_PROMPT.md:197`). NOT installed.
6. Credentials. No clause asks for tokens, passwords, cookies, or secret exfiltration. Nothing to install on that axis.
7. LibreOffice. `excel_validate_formulas.py` may shell out to LibreOffice when `--method auto` or `libreoffice` (`AGENT_SYSTEM_PROMPT.md:446-452`). NOT installed. Do not install LibreOffice for this run.

## Tool and package API the prompt assumes

The prompt assumes a checkout of excel-agent-tool and 15 CLI scripts, each one operation, JSON on stdout, exit codes 0 success, 1 error, 2 security error:

- Creation: `excel_create_new.py`, `excel_create_from_structure.py`, `excel_clone_template.py`
- Cells: `excel_set_value.py`, `excel_add_formula.py`, `excel_add_financial_input.py`, `excel_add_assumption.py`, `excel_get_value.py`
- Ranges: `excel_apply_range_formula.py`, `excel_format_range.py`
- Sheets: `excel_add_sheet.py`, `excel_export_sheet.py`
- Quality: `excel_validate_formulas.py`, `excel_repair_errors.py`
- Utility: `excel_get_info.py`

Invocation shape: `uv python tools/<name>.py --json` with `--file`, `--sheet`, `--cell`, `--formula`, `--output`, `--structure`. Shared library named by the README is `core/excel_agent_core.py`. Pinned `requirements.txt` is `openpyxl>=3.1.5`, `pandas>=2.3.2`, plus pytest packages. Optional external binary: LibreOffice Calc. Conventions the prompt treats as required: blue font for inputs, yellow fill for assumptions, black formulas, `--json` always.

None of `tools/` or `core/` was copied. `uv` was not installed.

## Verdict

Fit to keep as a local, untrusted reference for how that project wants an agent to call its CLI. Not fit to install as the live system prompt, and not fit to execute. The file is a shell-and-tool runbook for a package that is not present, it opens with a role override, and it documents a flag that disables its own formula network block. Task 2.a may append the file only behind a bridge that harness tools win and missing `excel_*.py` calls stay advisory. Task 2.b does not depend on this CLI. Workbook generation stays on `models/elite-luxury-mixed-use/SPEC.md` with python3 and openpyxl, as already delegated. Fetch did not fail, so this is not the "SPEC.md alone because the URL 404'd or the license forbids install" stop.
