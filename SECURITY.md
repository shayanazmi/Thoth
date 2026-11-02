# Security

Please report vulnerabilities **privately** through GitHub: open the repository's **Security** tab and choose
**Report a vulnerability**. Do not open a public issue for a security problem.

Thoth keeps provider keys only in `.env` (never committed), sanitises provider errors before logging them, and
stores your data in a local SQLite file. If you host Thoth for others, put it behind your own authentication:
the app has no user accounts.

---

<sub>Thoth · Developed by Shayan Azmi</sub>
