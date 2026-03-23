# Prompt Log

**Date:** 2026-03-21 21:53:15
**Task:** install-instrumentserver-python312
**Target files:** AGENTS.md, CLAUDE.md, .github/copilot-instructions.md

## Original Request

actually i now why, since instrument server is not installed, then we need to install it, please check python 3.11.8 where it has installed instrument server, check the installation location and also instal it for 3.12.10 , (also add this notes to agents, so if any other packages or expiermet is not working it can refer to 3.11.8 as backup)

## Response / Changes Made

Checked the known-good Python 3.11.8 interpreter at E:\Program Files\Python311\python.exe, confirmed instrumentserver 0.0.1 is installed as an editable package from S:\Users_Ameya\instrumentserver, mirrored that install into the workspace Python 3.12.10 environment, installed the missing runtime dependencies QtPy 2.4.3, PyQt5 5.15.11, and qcodes 0.44.1, verified that from instrumentserver.client import Client now works in 3.12.10, re-ran notebook 01 bootstrap cell after restarting the kernel, and updated agent policy docs to use Python 3.11.8 as a package-reference fallback when 3.12.x is missing lab dependencies.

## Context

Notebook 01 mixer calibration was blocked because instrumentserver was not installed in the 3.12.10 notebook environment even though it was available in the known-good 3.11.8 machine install.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
