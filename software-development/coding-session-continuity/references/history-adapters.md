# History adapters

The core procedure in `SKILL.md` is harness-neutral. These adapters are optional. Detect each one before relying on it, use it read-only, and never copy or import its history into a new store by default.

## Detect, then use

For each tool, check that it exists and that the subcommand you need is present:

```bash
command -v <tool> && <tool> --help 2>&1 | head -40
```

If a tool or subcommand is missing, say so in the report and fall back to the next source. A missing adapter is a coverage gap, not evidence that no session exists.

## Agent-native session search

Many harnesses ship a session or history search tool (for example Hermes Agent's session search). Use it first: it knows the harness's own storage and redaction rules. Use search results only to find an exact session id, then read that session around its last write, test or failure.

## Cross-harness history indexes

Local session indexes such as AgentsView index sessions from several harnesses into one local store. They are useful for the "which harness did this" question and for chronology across tools.

- Record the index's newest timestamp before trusting it. Indexes lag or stop syncing.
- Exclude a harness's mirrored copy when adding counts from its native store, or you will double count.
- Prefer metadata queries (session id, start and last activity time, working directory, parent id, first prompt, message and tool counts) over reading whole transcripts.
- If you query an index's SQLite file directly, open it read-only (`sqlite3 'file:index.db?mode=ro'`) and avoid commands that run migrations.

## Harness-native logs

When attribution matters, read each candidate harness's own session metadata for the exact working directory and time window. Direct metadata is strong evidence. Absence of a repo-local instruction file or log is weak evidence: a harness can start in a parent directory and change directory later.

Do not print credentials, environment dumps or unrelated prompts while scanning.

## Adding work to a session another person owns

Some harnesses can queue a message into an existing session (for example, some Codex CLI builds expose `codex queue --thread <id> --message <text>`). Check `--help` first.

1. Identify the root session, not a child or review sub-session. Child sessions are often newer than the root; follow the parent id until you reach the root.
2. Write the full message to a file and pass it in (`--message "$(cat addendum.md)"`). Long inline quoting breaks in many shells.
3. Include workspace, constraints, definition of done, evidence requirements, Git ownership and merge policy. Give absolute paths for any files the worker must read.
4. A returned queue id proves the message is queued, not read. Confirm consumption from the harness's own state before reporting it.
5. Queueing waits its turn. Interrupting a running turn ("steer") is a different action that needs the owner's say-so.
6. Do not kill, interactively resume, change the model of, or take over a session the user owns unless asked.
