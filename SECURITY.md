# Security policy

Mycelium is self-hosted. Departments and labs run it on their own machines and
keep their members' profiles, projects and conversations in it, so we treat a
security report as the most urgent kind of issue.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Report it privately through GitHub: on this repository, open the **Security**
tab and choose **Report a vulnerability**. Include what you found, how to
reproduce it, and what an attacker could do with it. A proof of concept is
welcome but not required.

What to expect:

- An acknowledgement within 5 working days.
- An assessment and a planned fix date within 14 days.
- Credit in the release notes when the fix ships, unless you would rather not.

Please give us a reasonable time to ship a fix before you disclose the issue
publicly, and do not test against an instance you do not run yourself.

## Supported versions

Only the latest release and the `main` branch receive security fixes. Update
before reporting if you can.

## Running it safely

The defaults are meant to be safe on a shared server: only the web gateway is
published, and only on `127.0.0.1` unless you choose otherwise; database and
cache passwords are generated at setup; debug mode is off. Before you serve
Mycelium beyond your own machine, read
[`docs/configuration.md`](docs/configuration.md) for TLS, backups and the
settings that control who may sign up.
