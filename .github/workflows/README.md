# GitHub Actions deployment

The `Telegram Bot` workflow has `workflow_dispatch`, so GitHub shows a **Run workflow** button in Actions.

Required repository secrets:

- `BOT_TOKEN`
- `ADMIN_IDS` (optional, but required for admin controls)
- `OPENROUTER_API_KEY` (optional)
- `OPENROUTER_MODEL` (optional)

Important: GitHub-hosted Actions runners are temporary. This workflow is useful for testing or temporary execution; it is not a reliable 24/7 hosting solution for a Telegram polling bot.
