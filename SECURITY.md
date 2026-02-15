# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 1.x     | Yes                |
| < 1.0   | No                 |

## Reporting a Vulnerability

If you discover a security vulnerability in bac-py, please report it
responsibly. **Do not open a public GitHub issue.**

Email **jscott3201@gmail.com** with:

- A description of the vulnerability
- Steps to reproduce
- Affected versions
- Any potential impact assessment

You should receive an acknowledgment within 48 hours. We will work with you to
understand the issue and coordinate a fix before any public disclosure.

## Security Considerations

bac-py implements the BACnet protocol, which is commonly used in building
automation and industrial control systems. Key security areas:

- **BACnet Secure Connect (Annex AB):** TLS 1.3 transport with mutual
  certificate authentication. Always use TLS in production environments.
- **Input validation:** All decode paths validate buffer bounds, tag lengths,
  and nesting depth.
- **Logging:** Credentials and keys are never included in log output or error
  messages.
- **Resource limits:** Allocation caps on nesting depth, decoded values, and
  queue sizes to prevent resource exhaustion.
