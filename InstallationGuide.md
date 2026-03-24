# HomeClaw Installation Guide

This guide focuses on installation and recovery.

If you want the fastest path, use `QuickStart.md`.

---

## 1) Install (recommended)

| Platform | Command |
|---|---|
| macOS / Linux | `bash install.sh` |
| Windows | `install.bat` (or `.\install.ps1`) |

What installer does:

- dependency setup (Python + Node)
- optional helper CLIs
- VMPrint install/build
- opens Portal (`http://127.0.0.1:18472`)

---

## 2) Verify

```bash
python -m main doctor
```

If doctor reports issues, fix them before production use.

---

## 3) Common problems

### Script permission denied (macOS/Linux)

Use:

```bash
bash install.sh
```

### PowerShell execution policy (Windows)

Use `install.bat`, or:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

### pip 403 / mirror issues

Use official index:

```bash
pip install -r requirements.txt -i https://pypi.org/simple
```

### VMPrint build errors

Run from VMPrint root:

```bash
cd tools/vmprint
npm install
npm run build
```

---

## 4) Manual install (fallback)

```bash
git clone https://github.com/allenpeng0705/HomeClaw.git
cd HomeClaw
pip install -r requirements.txt
```

Then:

- configure models in `config/llm.yml`
- start Portal `python -m main portal`
- start Core `python -m main start`

---

## 5) Install outputs (important)

After successful install:

- Portal available at `http://127.0.0.1:18472`
- Core can be started with `python -m main start`
- docs and config are ready
- VMPrint path should exist at `tools/vmprint`

---

More:

- `QuickStart.md`
- `HOW_TO_USE.md`
- `docs/install.md`
