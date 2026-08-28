# Security

Never commit secrets. API keys are server-side only, encrypted at rest, masked in UI, and least-privilege. Withdrawal permissions must never be required. Validate authorization server-side. Rate-limit auth and exchange endpoints. Record security-sensitive actions in the audit log.
