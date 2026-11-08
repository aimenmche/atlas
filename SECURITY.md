# Security policy

Atlas handles local datasets, so a security report is taken seriously even
though the project is a single-user local application.

## Supported versions

| Version | Supported |
| --- | --- |
| 1.x | Yes |
| < 1.0 | No |

## Reporting a vulnerability

Please do **not** open a public issue for a suspected vulnerability.

Use GitHub's private vulnerability reporting:

1. Open the repository's **Security** tab.
2. Choose **Report a vulnerability**.
3. Include the Atlas version, operating system, reproduction steps, and the
   smallest dataset or request that demonstrates the issue.

If private reporting is unavailable, contact the maintainer listed in
`pyproject.toml` and ask for a private channel before sharing details.

You can expect an acknowledgement within seven days and a status update within
fourteen days. Please allow time for a fix before public disclosure.

## Scope

In scope:

- the read-only SQL guard, query timeout, and row caps
- upload parsing and archive handling
- the local HTTP API, including SSE and report generation
- cross-site request handling and browser security headers
- the optional OpenAI-compatible model path
- dependency and packaging issues

Out of scope:

- an attacker who already has read access to the local data directory
- denial of service against a machine you control with intentionally huge files
- vulnerabilities in a model endpoint you configure yourself
- reports that require exposing Atlas to the public internet without a reverse
  proxy, authentication, and TLS

## Operating safely

Atlas binds to `127.0.0.1` by default. If you bind it to another interface, put
it behind a reverse proxy that provides authentication and TLS. Do not store
secrets in the data directory or commit `data/`, which is ignored by default.

## Disclosure

Once a fix is available, the report and remediation are summarized in the
release notes with credit to the reporter unless anonymity is requested.
