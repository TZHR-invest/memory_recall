# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Memory Recall, please report it privately.

**Do not** open a public issue. Instead, contact the maintainers directly:

- **GitHub Issues**: https://github.com/TZHR-invest/memory_recall/issues
- For sensitive issues, please reach out to the repository administrators directly.

We will acknowledge receipt within 48 hours and provide an estimated timeline for a fix.

## Scope

This security policy covers:
- The Memory Recall API server (`apps/api/`)
- Memory Recall plugins (`apps/api/src/plugins/`)
- The web frontend (`web/`)

## Best Practices

When deploying Memory Recall:

1. **API Keys**: Always use environment variables (`.env`) for secrets. Never hardcode API keys.
2. **Database**: Use strong passwords for PostgreSQL. Restrict network access.
3. **Authentication**: Enable API Key authentication in production. Never expose the service without authentication.
4. **HTTPS**: Use a reverse proxy (nginx, Caddy) with TLS in production.
5. **Updates**: Keep dependencies updated to patch security vulnerabilities.
