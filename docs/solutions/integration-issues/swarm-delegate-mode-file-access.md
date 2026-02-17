---
title: Swarm agents lose file tools in delegate mode
category: integration-issues
tags: [swarm, delegate-mode, claude-code, team-coordination]
module: film_parser
symptoms:
  - Spawned teammate agents report "No such tool available: Read"
  - Agents can only use Task/SendMessage tools
  - Agents request file contents via chat instead of reading directly
severity: high
date_resolved: 2026-02-16
---

# Swarm Agents Lose File Tools in Delegate Mode

## Problem

When using Claude Code's TeamCreate to spawn a swarm of agents, agents spawned
**after entering delegate mode** only receive Task management and SendMessage
tools. They cannot read files, write files, or run bash commands — making them
unable to complete code-writing tasks.

## Symptoms

- Agent reports: `Error: No such tool available: Read`
- Agent messages team lead asking for file contents to be shared via chat
- Agent can create/update tasks but cannot interact with the filesystem
- Occurs for agents spawned via `Task` tool while in delegate mode

## Root Cause

Delegate mode restricts the team lead to coordination-only tools (Task*, SendMessage).
When spawning new teammates from within delegate mode, the spawned agents inherit
the restricted tool context. The `mode: bypassPermissions` parameter on the Task
tool controls permission prompts but does **not** override the delegate mode tool
restriction for the spawned agent.

## Solution

Spawn all agents that need file access **before** entering delegate mode, or use
`subagent_type: general-purpose` with file-heavy tasks delegated to standalone
Task agents (not team members).

### What worked

Agents spawned in the initial `Task` calls (before delegate mode activated) had
full tool access and completed their tasks. Agents spawned later (classifier-agent,
cli-agent) were restricted.

### Workaround used

1. Shut down the restricted agent
2. Delete the team (`TeamDelete`) to exit delegate mode
3. Spawn a standalone `Task` agent (not a teammate) with `mode: bypassPermissions`
4. The standalone agent has full tool access and completes the work

```python
# This works — standalone agent outside delegate mode
Task(
    description="Build cli.py",
    prompt="...",
    subagent_type="general-purpose",
    mode="bypassPermissions",
)

# This fails — teammate spawned during delegate mode
Task(
    description="Build cli.py",
    prompt="...",
    subagent_type="general-purpose",
    name="cli-agent",
    team_name="film-parser-build",  # <-- triggers delegate mode context
    mode="bypassPermissions",
    run_in_background=True,
)
```

## Prevention

- Spawn all file-writing agents in the first batch, before TeamCreate activates delegate mode
- For late-stage tasks that need file access, exit delegate mode first (TeamDelete), then use standalone Task agents
- Keep the team pattern for coordination-only: task tracking, message passing, progress monitoring
- File-heavy integration tasks (like cli.py that imports all modules) are better handled by the lead agent or a standalone Task agent

## Related

- Claude Code Teams documentation
- Fan-out/fan-in swarm pattern for parallel module builds
