# Contributing

Thanks for helping improve the project. Start with the setup and validation commands in
the README. Please keep the API, worker, and web application independently buildable, and
use Python 3.12+ and Node.js 22.12+.

Before submitting a change:

1. Run the Python tests, Ruff checks, and frontend build.
2. For container changes, run `docker compose up --build -d --wait` followed by
   `python scripts/smoke_test.py`.
3. Add tests for new behavior, document configuration, and update event contracts
   when an event changes.
4. Keep secrets, generated datasets, model binaries, virtual environments, and
   dependency directories out of version control.

Use Ruff for Python formatting and linting. Keep TypeScript strict checks enabled.
In a pull request, explain what changed from a user's point of view and include the checks
you ran. If something couldn't be tested, say so plainly.
