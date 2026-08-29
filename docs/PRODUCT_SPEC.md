# QuantEdge Commercial Product Spec
## Product
QuantEdge is a premium market-intelligence platform built around setup detection rather than forced predictions.
## Signal contract
A signal is eligible only after market structure, trend, trigger, momentum, volume and multi-timeframe checks align. Otherwise return NO_TRADE/FORMING. Confidence describes the validated setup; it does not create the setup.
## Access
Free tier: limited market access and a 3-day trial. Premium tiers: expanded markets, real-time alerts, advanced analytics and history.
## Security
Accounts are server-authoritative. Subscription entitlement is checked server-side. Sessions are revocable. New-device verification and concurrent-session controls are required; fingerprinting is only a supporting risk signal, never the sole identity control.
## Commercial
Billing must use a PCI-compliant payment provider; the application must never store raw card data. Webhooks are the source of truth for subscription state.
## Quality gate
No production release until build, typecheck, unit tests, API health, market-data error handling, authentication/authorization, billing webhook verification, rate limits, and end-to-end smoke tests pass.