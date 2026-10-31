# Privacy

Refinish is a skill: instructions and Python scripts that your agent runs. It has no server, no account and no telemetry.

- **What it reads**: only the pictures and files you point it at.
- **What it writes**: the finished pictures and its working files (subject files, part maps, review sheets), in the folders you choose. Nothing is written anywhere else.
- **What it sends**: nothing. The scripts make no network requests. If its Python packages (NumPy, SciPy, OpenCV) are missing, the agent installs them from PyPI once, as step 0 of `SKILL.md` says; that download sends none of your data.
- **What it keeps**: nothing. There is no Refinish service to keep anything.

Where the scripts run depends on your agent: on your computer in Claude Code, Codex or Cowork, or in the agent's own sandbox in a chat. What you send to the agent, the pictures included, is covered by that agent's privacy policy.

Questions: open an issue at https://github.com/owoevan-dev/refinish-skill/issues.
