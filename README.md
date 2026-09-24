# fig.py — Figma from the terminal

Single-file CLI. No pip installs needed (Python 3.8+, stdlib only).

## Setup (one time)

1. Create a token: Figma → your avatar → **Settings** → **Personal access tokens**
   → Generate. "File content: read" scope is enough for everything below.
2. Save it next to the script:
   - On this machine: `python fig.py save-token`
   - PowerShell: `[IO.File]::WriteAllText("$pwd\.figma_token", (Read-Host "Paste Figma token").Trim())`

Token lookup order: `--token` flag → `FIGMA_TOKEN` env var → `.figma_token` file.

## Commands

```
python fig.py me                                    # who owns the token
python fig.py pages FILE_KEY                        # list pages
python fig.py file FILE_KEY                         # outline: pages -> top frames
python fig.py file FILE_KEY --json --out doc.json   # full document JSON
python fig.py file FILE_KEY --nodes 0:1,2:3         # specific nodes
python fig.py components FILE_KEY                   # list components
python fig.py styles FILE_KEY                       # list styles
python fig.py comments FILE_KEY                     # read comments + replies
python fig.py export FILE_KEY --ids 0:1,2:3 --format png --scale 2 --out ./shots
python fig.py projects TEAM_ID                      # list team projects
python fig.py project-files PROJECT_ID              # list files in a project
python fig.py open FILE_KEY                         # print the figma.com URL
```

Find `FILE_KEY` in any Figma URL: `figma.com/design/<FILE_KEY>/...`.
`TEAM_ID` is in the team URL: `figma.com/files/team/<TEAM_ID>/...`.
`PROJECT_ID` is in the project URL: `figma.com/files/project/<PROJECT_ID>/...`.
