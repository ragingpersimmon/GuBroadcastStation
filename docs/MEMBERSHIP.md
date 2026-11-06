# Sign-in + membership: runbook

Code: `gbs/account/server.py` (service), `gbs/site/build.py` `page_account` (pages),
`config/membership.json` (plans). Service: `gubroadcast-account.service` on
127.0.0.1:8710; nginx proxies `/auth/` and `/billing/` to it. Members live in
`$GBS_DATA_DIR/members.db`. Same shape as the flowerseekingbee.com Hive membership.

Everything is off until its keys are in `/opt/gubroadcast/.env`. Sign-in buttons
appear for each provider with a client id + secret. A plan's Join button appears
once Stripe is on and that plan has a price id. After editing `.env`:
`sudo bash /opt/gubroadcast/deploy/update.sh` (restarts the service, rebuilds pages).

## 1. Sign-in providers

Redirect URI for every provider: `https://gubs.ca/auth/<provider>/callback`.

| Provider | Where | Keys |
|---|---|---|
| Google | console.cloud.google.com → APIs & Services → Credentials → OAuth client ID (Web). Consent screen: app name "Gu Broadcasting Station", scopes email/profile/openid, publish to production. | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| Microsoft | entra.microsoft.com → App registrations → New (accounts in any org + personal). Certificates & secrets → new secret. | `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET` |
| GitHub | github.com/settings/developers → New OAuth App. | `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` |
| Facebook | developers.facebook.com → Create app → Facebook Login. Needs a privacy policy URL (`https://gubs.ca/privacy/`) and app review to go live. | `FACEBOOK_CLIENT_ID`, `FACEBOOK_CLIENT_SECRET` |

Sign in with Apple is not wired: it needs a paid Apple Developer account and a
signed (ES256) client secret. Add it later if wanted.

Check: `curl -s https://gubs.ca/auth/health` lists enabled providers.

## 2. Stripe (test mode first)

1. Account: a Stripe account for Gu (or a new business in Ric's existing Stripe login), Canada.
   Website `https://gubs.ca`; terms `/terms/`, privacy `/privacy/`, refund policy is in `/membership/` and `/terms/`.
2. Product "Gu Broadcasting Station membership" with three prices (CAD), matching `config/membership.json`:
   CA$9 monthly recurring → `STRIPE_PRICE_MONTHLY`; CA$89 yearly recurring → `STRIPE_PRICE_YEARLY`;
   CA$365 one-time → `STRIPE_PRICE_FOUNDING` (first 100, lifetime).
3. Restricted key "gubs-site": write Checkout Sessions, Customer portal, Customers, Subscriptions; read Prices
   → `STRIPE_SECRET_KEY`.
4. Webhook `https://gubs.ca/billing/webhook`, events `checkout.session.completed`,
   `customer.subscription.created|updated|deleted` → signing secret `STRIPE_WEBHOOK_SECRET`.
5. Customer portal: allow cancel (end of period) and update payment method; return URL `https://gubs.ca/account/`.
6. Branding: name Gu Broadcasting Station, colour `#b5121b`; statement descriptor `GUBS.CA`.

Test: sign in, Join → card `4242 4242 4242 4242` → `/membership/thanks/` → `/account/` shows the plan
and ads disappear. Then swap test keys and price ids for live ones.

## What members get (keep it true)

No ads on gubs.ca (ad slots hidden via the `gu_m` flag), a member badge on the account page, and for
Founding Members lifetime membership. Edit perks in `config/membership.json`; don't promise anything
the site doesn't do.
