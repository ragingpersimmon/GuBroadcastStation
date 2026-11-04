# The Gu Briefing: newsletter

## The decisions

| Question | Answer |
|---|---|
| Purpose | The day's world news in about 3 minutes, every story linked to the outlets that reported it. |
| Audience | People who want a fast, sourced overview, not another opinion feed. |
| Angle | Sources-first summaries from an AI newsroom that shows its work: every link, every outlet, every correction. |
| Cadence | Weekdays, built 05:45 Pacific, sent about 06:00 (`gubroadcast-newsletter.timer`). Stick to it. |
| Platform | **Kit (kit.com), free Newsletter plan**: up to 10,000 subscribers, unlimited broadcasts, double opt-in forms, API on the free plan. Beehiiv's create-post API needs Max/Enterprise, and Substack has no API, so neither can run unattended. |
| Format | Harold Yi's signature open, 3 top stories, 1–2 headlines per desk, market pulse + weather, at most one labelled sponsor. Same shape every day. |

## How it runs

`python -m gbs newsletter build` writes today's issue to `data/newsletter/issues/<date>.json` and refreshes
`/newsletter/` (sign-up, issue archive, web copy of every issue).

`python -m gbs newsletter send` builds the issue and hands it to the provider (`GBS_NEWSLETTER_PROVIDER`):

- `file` (default): writes `data/newsletter/outbox/<date>.html` + `.txt`. No email is sent. Use it to check a week of issues before launch.
- `kit`: creates a Kit broadcast through the v4 API, scheduled `KIT_SEND_DELAY_MIN` (10) minutes ahead, so a bad issue can still be cancelled in Kit. It sends at most once per day; `--force` overrides.

If fewer than 2 top stories were published in the last 24 hours, no issue is built.

## Setup: Ric

### 1. Kit account
1. Sign up at kit.com on the free **Newsletter** plan with a @gubs.ca address (T11c forwarding must work first).
2. **Settings → Account → Sending address:** `news@gubs.ca`. **Mailing address:** a real postal address, which Kit prints in every footer. CASL and CAN-SPAM require one. A PO box or virtual mailbox is fine if you don't want your home address published.
3. **Settings → Developer:** create a **v4 API key**. Put it in `/opt/gubroadcast/.env` as `KIT_API_KEY=`.
4. **Email templates:** pick or make a *Classic* template (simple, white). Our HTML is the body and Kit adds the footer. Optionally set its id as `KIT_EMAIL_TEMPLATE_ID`.

### 2. Domain authentication (deliverability, required for bulk senders)
In Kit: **Settings → Email → Domain authentication → gubs.ca**. Kit shows the exact records. Add them in Namecheap Advanced DNS:

| Type | Host | Value |
|---|---|---|
| CNAME | the DKIM hosts Kit shows (e.g. `ckespa._domainkey`) | the targets Kit shows |
| CNAME / TXT | any return-path / verification host Kit shows | as shown |
| TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:news@gubs.ca` (move to `p=quarantine` after a few clean weeks) |

**SPF:** a domain can have only **one** SPF record. Namecheap's email forwarding already manages `v=spf1 include:spf.efwd.registrar-servers.com ~all` on `@`. If Kit asks for an SPF include, don't add a second record; ask Namecheap support to merge it, or rely on Kit's DKIM/return-path, which is what authenticates its mail. Click **Verify** in Kit once the records are live.

### 3. Sign-up form (double opt-in)
1. **Grow → Landing pages & forms → new inline form** named "Gu Briefing".
2. **Settings → Incentive:** turn **double opt-in ON** (Kit sends the confirmation email).
   - Confirmation email subject: `Confirm your Gu Briefing subscription`
   - Body: use "Email 1" below.
   - After confirming, redirect to `https://gubs.ca/newsletter/confirmed/`.
3. **Settings → General → After subscribing:** redirect to `https://gubs.ca/newsletter/thanks/`.
4. **Embed → HTML:** copy the `<form action="...">` URL (it ends `/forms/<ID>/subscriptions`) into `config/site.json` → `newsletter.action`. The email field name is `email_address` (`newsletter.email_field`). Rebuild the site, and `/newsletter/` stops saying "launching soon".

### 4. Go live
1. Leave `GBS_NEWSLETTER_PROVIDER=file` for a few weekdays and read the outbox issues.
2. Send yourself a test: subscribe with your own address, set `GBS_NEWSLETTER_PROVIDER=kit`, run `python -m gbs newsletter send`, and check Kit → Broadcasts (scheduled).
3. Leave `kit` set. The timer does the rest.

## Welcome flow

The free plan includes the double opt-in confirmation email but not sequences, so the welcome is split: the confirmation email (Email 1) plus the `/newsletter/confirmed/` page, which sets expectations, delivers the guide and asks a question. Emails 2–3 need Kit's Creator plan; they're drafted below for when you upgrade.

**Email 1: confirmation (sent immediately by Kit)**
> Subject: Confirm your Gu Briefing subscription
>
> GUUd morning (or whenever you're reading this). One click and you're in: [Confirm my subscription]
>
> From the next weekday at 6 a.m. Pacific you'll get The Gu Briefing: the top stories in about three minutes, each one linked to the outlets that reported it.
>
> Didn't sign up? Ignore this email and you won't hear from us again.

**Email 2: welcome (Creator plan sequence, day 0 after confirm)**
> Subject: Welcome to The Gu Briefing
>
> This is Harold Yi at Gu Broadcasting Station, where we follow the story for your better insight.
>
> Here's what to expect: three top stories, a headline or two from every desk, the market pulse and your local forecast, weekday mornings. Every Gu anchor is an AI-generated character, and every fact comes from a newsroom we link to.
>
> Your free guide: How to read a news story in 60 seconds → gubs.ca/newsletter/guide/
>
> One question: which part of the world do you think we under-cover? Hit reply. We read every answer.

**Email 3: how Gu works (Creator plan sequence, day 3)**
> Subject: How an AI newsroom shows its work
>
> Short version: we read established outlets, summarize in our own words, link every source, and correct mistakes in public. The long version: gubs.ca/about/ai/ · Our standards: gubs.ca/about/standards/
>
> If a story ever looks wrong, reply to any issue.

## Growth and list hygiene

- **Measure** replies and clicks (our links carry `utm_source=gu-briefing&utm_medium=email&utm_campaign=briefing-<date>`), not opens.
- **Bounces:** Kit removes hard bounces automatically.
- **Prune:** every quarter, in Kit, tag subscribers with no opens or clicks in 90 days, send them one "still want this?" broadcast, then unsubscribe anyone who doesn't respond. This protects sender reputation.
- **Monetize later:** one labelled sponsor slot per issue (`config/sponsors.json`, same rules as on air). Paid recommendations and paid tiers come after the list is engaged.

## CASL checklist (Canada)

- [x] Express consent: double opt-in form; Kit keeps the consent record (time, IP, form).
- [x] Sender identified: name (Gu Broadcasting Station) and reply-to in every issue.
- [ ] Mailing address in every footer: set in Kit (step 1.2).
- [x] Unsubscribe in every issue, honoured immediately: Kit footer.
- [x] No buying or importing lists.
