# Проблемы и их решения (Troubleshooting Log)

*Этот файл предназначен для фиксации всех значимых проблем, возникающих в ходе разработки и эксплуатации проекта. Старые проблемы не удаляются, так как история их решения является важной частью документации.*

## Шаблон для новой записи

```markdown
# Problem: <название>
Date: 
Environment: 
Symptoms: 
What was expected: 
What happened: 
Root cause: 
Solution: 
Verification: 
Prevention: 
Related files: 
```

---

# Problem: Docker is missing on local Windows environment
Date: 2026-08-11
Environment: Local Windows Host
Symptoms: `docker` command is not recognized in PowerShell (`CommandNotFoundException`).
What was expected: Docker Desktop or Docker Engine should be available to spin up PostgreSQL and Redis containers for Phase 1.5 validation.
What happened: Validation Step 1 failed because the `docker` CLI is missing.
Root cause: Docker Desktop is not installed or not added to PATH on this Windows machine.
Solution: User needs to install Docker Desktop for Windows or use an alternative environment (like WSL2 with Docker) to run local containerized infrastructure.
Verification: N/A (Blocked)
Prevention: Ensure local environment prerequisites are met before attempting full-stack validation.
---

# Problem: Insufficient RAM on Staging Server
Date: 2026-08-11
Environment: Staging VPS Host
Symptoms: Staging deployment blocked by safety checks.
What was expected: At least 2 GB of free RAM to safely spin up staging Docker containers (PostgreSQL, Redis).
What happened: The `free -m` command reported only 164 MB of free RAM available.
Root cause: The server is currently running multiple production services (PostgreSQL 14, Nginx, n8n, multiple bots, etc.) that consume most of the 2GB total memory.
Solution: User must either upgrade the VPS plan to provide more RAM, stop non-critical services temporarily, or provide an alternative staging server with sufficient resources.
Verification: Ran `free -m` via SSH.
Prevention: Resource limits validation step successfully prevented potential OOM (Out Of Memory) crashes on the production server.
Related files: `docs/staging/STAGING_BASELINE.md`
