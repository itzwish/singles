# Contributing to Easy Single

Thanks for taking the time to contribute! 🎉

## How to contribute

### Reporting a bug

1. Search the [issue tracker](https://github.com/314159ctl/virtual-gf/issues) to see if it already exists
2. If not, open a new issue describing:
   - Your environment (OS, Python version, etc.)
   - Steps to reproduce
   - Expected behaviour vs. actual behaviour
   - Relevant screenshots or logs

### Submitting code

1. Fork this repository
2. Create a feature branch:
   ```bash
   git checkout -b feat/your-feature
   ```
3. Follow the existing code style
4. Make sure the tests pass
5. Commit and push:
   ```bash
   git commit -m "feat: short description of your change"
   git push origin feat/your-feature
   ```
6. Open a pull request describing your change

### Commit convention

Use the usual prefixes:
- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation change
- `refactor:` — code refactor
- `chore:` — build/tooling change

## Development setup

Follow the Quick Start section of [README.md](./README.md) to get a local
development environment running.

## Code style

- Python: follow PEP 8
- Vue/TypeScript: type-check with `vue-tsc`