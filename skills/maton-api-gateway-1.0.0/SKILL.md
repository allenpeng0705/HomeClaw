---
name: maton-api-gateway
description: |
  Call 100+ third-party APIs (Slack, HubSpot, Outlook, Notion, Google Workspace, Airtable, Salesforce, Stripe, etc.) with a single API key via Maton. Use when the user wants to interact with any of these services and you have MATON_API_KEY set.
keywords: [slack, linkedin, outlook, hubspot, notion, gmail, stripe, google calendar, google sheets, salesforce, airtable, calendly, github, maton, api gateway]
compatibility: Requires network access and MATON_API_KEY (get key at maton.ai/settings; connect each app via OAuth at maton.ai)
trigger:
  patterns: ["maton|api gateway|gateway\\.maton|maton\\.ai.*connect|connect.*(slack|hubspot|notion|salesforce|stripe).*api|post.*linkedin|发送.*linkedin|发.*领英|linkedin.*post|publish.*linkedin|share.*linkedin|send.*slack|slack.*message|outlook.*(email|mail|calendar)|hubspot.*(contact|deal)|notion.*(database|page)|gmail|google.*calendar|google.*sheet|stripe.*(customer|payment)|salesforce|airtable|calendly|github.*(repo|issue|pr)"]
  instruction: "User asked to use an external service (Slack, LinkedIn, Outlook, HubSpot, Notion, Gmail, Stripe, etc.). Use run_skill(skill_name='maton-api-gateway-1.0.0', script='request.py') with app and path from this skill's Supported Services table and references/. For LinkedIn post: GET linkedin/rest/me then POST linkedin/rest/posts with commentary. Do not reply that the action was done without calling the skill."
---

# Maton API Gateway

Call native third-party APIs through [Maton](https://maton.ai) with managed OAuth. **One API token** (`MATON_API_KEY`) is all you need: after you connect each app once at [maton.ai](https://www.maton.ai/) (Connections), that single token lets you access every connected service. The **references/** folder in this skill tells HomeClaw how to call each service—paths, methods, and examples—so the model can use the gateway for Slack, HubSpot, Outlook, Notion, and 100+ others.

## When to use this skill

Use **run_skill(skill_name='maton-api-gateway-1.0.0', script='request.py')** when the user asks to do any of the following (connect each app once at [maton.ai](https://www.maton.ai/) first):

| User asks to… | app | Path / action (see references/) |
|---------------|-----|----------------------------------|
| Send Slack message, list channels | `slack` | e.g. `api/chat.postMessage`, `api/conversations.list` |
| Post to LinkedIn, get profile | `linkedin` | `rest/me`, `rest/posts` (POST with commentary) |
| Outlook email, calendar, contacts | `outlook` | `v1.0/me/messages`, `v1.0/me/events`, etc. |
| Gmail send, list, search | `google-mail` | `gmail/v1/users/me/messages` |
| HubSpot contacts, deals, companies | `hubspot` | `crm/v3/objects/contacts`, etc. |
| Notion databases, pages, search | `notion` | See references/notion.md |
| Google Calendar events | `google-calendar` | `calendar/v3/events` |
| Google Sheets read/append | `google-sheets` | `sheets/v4/spreadsheets` |
| Stripe customers, payments | `stripe` | `v1/customers`, `v1/charges` |
| Salesforce SOQL, contacts | `salesforce` | See references/salesforce.md |
| Airtable bases, records | `airtable` | `v0/{baseId}/{tableId}` |
| Calendly events, availability | `calendly` | See references/calendly.md |
| GitHub repos, issues, PRs | `github` | `repos`, `issues`, etc. |

**App name** must match the Supported Services table below. **Path** is the native API path for that service (references/ files have examples). **Do not** claim the action was done without calling the skill.

## How users ask (natural language)

Users **don’t need to know API paths or URLs**. They say what they want in plain language; the model uses this skill and the references to choose the right `app` and `path`, then calls `request.py`. Example things users can say:

- “Send a Slack message to #general: Hello team”
- “List my last 10 Outlook emails”
- “Create a HubSpot contact: John, john@example.com”
- “What’s on my Google Calendar today?”
- “Add a row to my Google Sheet …”
- “List my Notion databases”
- “Create a Stripe customer …”

**For a full list of example phrases per service**, see **USAGE.md** in this skill folder. Point users there so they know what they can ask.

## Quick Start (run_skill)

Prefer **run_skill** with script `request.py` so the model can call the gateway without constructing raw HTTP:

- **run_skill**(skill_name=`maton-api-gateway-1.0.0`, script=`request.py`, args=[`slack`, `api/chat.postMessage`, `POST`, `{"channel":"C0123456","text":"Hello!"}`])

Arguments: `app`, `path`, `method` (optional, default GET), `body` (optional, JSON string). Optional 5th arg: `connection_id` for `Maton-Connection` header.

**API key:** Set `MATON_API_KEY` in the environment where Core runs, or set `maton_api_key` in this skill's `config.yml` (env overrides config). Get key at [maton.ai/settings](https://www.maton.ai/settings).

If run_skill is not available or you need connection management, use the Python snippets below (exec).

## Base URL

```
https://gateway.maton.ai/{app}/{native-api-path}
```

- `{app}` = service name (e.g. `slack`, `outlook`, `hubspot`, `google-mail`, `notion`). **Must** match the app name so the gateway uses the right OAuth connection.
- `{native-api-path}` = the actual API path (e.g. Slack: `api/chat.postMessage`, Outlook: `v1.0/me/messages`).

Example: Gmail path is `gmail/v1/users/me/messages` → full URL: `https://gateway.maton.ai/google-mail/gmail/v1/users/me/messages`.

## Authentication

All requests: `Authorization: Bearer $MATON_API_KEY`. Set the key either:

- **Environment:** `export MATON_API_KEY="YOUR_KEY"` where Core runs, or
- **Skill config:** In `skills/maton-api-gateway-1.0.0/config.yml` set `maton_api_key: "YOUR_KEY"` (env overrides config).

Get key at [maton.ai/settings](https://www.maton.ai/settings).

## Connection Management

Control plane: `https://ctrl.maton.ai`.

- **List:** `GET https://ctrl.maton.ai/connections?app=slack&status=ACTIVE`
- **Create:** `POST https://ctrl.maton.ai/connections` body `{"app": "slack"}` → response has `url`; open in browser to complete OAuth.
- **Get:** `GET https://ctrl.maton.ai/connections/{connection_id}`
- **Delete:** `DELETE https://ctrl.maton.ai/connections/{connection_id}`

If you have multiple connections for one app, send header `Maton-Connection: {connection_id}` on gateway requests; otherwise the gateway uses the default (oldest active) connection.

## Supported Services

Full table from [Maton api-gateway-skill](https://github.com/maton-ai/api-gateway-skill). Use `{app}` as the first path segment: `https://gateway.maton.ai/{app}/{native-api-path}`.

| Service | App Name | Base URL Proxied |
|---------|----------|------------------|
| ActiveCampaign | `active-campaign` | `{account}.api-us1.com` |
| Acuity Scheduling | `acuity-scheduling` | `acuityscheduling.com` |
| Airtable | `airtable` | `api.airtable.com` |
| Apollo | `apollo` | `api.apollo.io` |
| Asana | `asana` | `app.asana.com` |
| Attio | `attio` | `api.attio.com` |
| Basecamp | `basecamp` | `3.basecampapi.com` |
| beehiiv | `beehiiv` | `api.beehiiv.com` |
| Box | `box` | `api.box.com` |
| Brevo | `brevo` | `api.brevo.com` |
| Calendly | `calendly` | `api.calendly.com` |
| Cal.com | `cal-com` | `api.cal.com` |
| CallRail | `callrail` | `api.callrail.com` |
| Chargebee | `chargebee` | `{subdomain}.chargebee.com` |
| ClickFunnels | `clickfunnels` | `{subdomain}.myclickfunnels.com` |
| ClickSend | `clicksend` | `rest.clicksend.com` |
| ClickUp | `clickup` | `api.clickup.com` |
| Clockify | `clockify` | `api.clockify.me` |
| Coda | `coda` | `coda.io` |
| Confluence | `confluence` | `api.atlassian.com` |
| CompanyCam | `companycam` | `api.companycam.com` |
| Cognito Forms | `cognito-forms` | `www.cognitoforms.com` |
| Constant Contact | `constant-contact` | `api.cc.email` |
| Dropbox | `dropbox` | `api.dropboxapi.com` |
| Dropbox Business | `dropbox-business` | `api.dropboxapi.com` |
| ElevenLabs | `elevenlabs` | `api.elevenlabs.io` |
| Eventbrite | `eventbrite` | `www.eventbriteapi.com` |
| Fathom | `fathom` | `api.fathom.ai` |
| Firebase | `firebase` | `firebase.googleapis.com` |
| Fireflies | `fireflies` | `api.fireflies.ai` |
| GetResponse | `getresponse` | `api.getresponse.com` |
| GitHub | `github` | `api.github.com` |
| Gumroad | `gumroad` | `api.gumroad.com` |
| Google Ads | `google-ads` | `googleads.googleapis.com` |
| Google BigQuery | `google-bigquery` | `bigquery.googleapis.com` |
| Google Analytics Admin | `google-analytics-admin` | `analyticsadmin.googleapis.com` |
| Google Analytics Data | `google-analytics-data` | `analyticsdata.googleapis.com` |
| Google Calendar | `google-calendar` | `www.googleapis.com` |
| Google Classroom | `google-classroom` | `classroom.googleapis.com` |
| Google Contacts | `google-contacts` | `people.googleapis.com` |
| Google Docs | `google-docs` | `docs.googleapis.com` |
| Google Drive | `google-drive` | `www.googleapis.com` |
| Google Forms | `google-forms` | `forms.googleapis.com` |
| Gmail | `google-mail` | `gmail.googleapis.com` |
| Google Merchant | `google-merchant` | `merchantapi.googleapis.com` |
| Google Meet | `google-meet` | `meet.googleapis.com` |
| Google Play | `google-play` | `androidpublisher.googleapis.com` |
| Google Search Console | `google-search-console` | `www.googleapis.com` |
| Google Sheets | `google-sheets` | `sheets.googleapis.com` |
| Google Slides | `google-slides` | `slides.googleapis.com` |
| Google Tasks | `google-tasks` | `tasks.googleapis.com` |
| Google Workspace Admin | `google-workspace-admin` | `admin.googleapis.com` |
| HubSpot | `hubspot` | `api.hubapi.com` |
| Instantly | `instantly` | `api.instantly.ai` |
| Jira | `jira` | `api.atlassian.com` |
| Jobber | `jobber` | `api.getjobber.com` |
| JotForm | `jotform` | `api.jotform.com` |
| Keap | `keap` | `api.infusionsoft.com` |
| Kit | `kit` | `api.kit.com` |
| Klaviyo | `klaviyo` | `a.klaviyo.com` |
| Lemlist | `lemlist` | `api.lemlist.com` |
| Linear | `linear` | `api.linear.app` |
| LinkedIn | `linkedin` | `api.linkedin.com` |
| Mailchimp | `mailchimp` | `{dc}.api.mailchimp.com` |
| MailerLite | `mailerlite` | `connect.mailerlite.com` |
| Mailgun | `mailgun` | `api.mailgun.net` |
| ManyChat | `manychat` | `api.manychat.com` |
| Microsoft Excel | `microsoft-excel` | `graph.microsoft.com` |
| Microsoft Teams | `microsoft-teams` | `graph.microsoft.com` |
| Microsoft To Do | `microsoft-to-do` | `graph.microsoft.com` |
| Monday.com | `monday` | `api.monday.com` |
| Motion | `motion` | `api.usemotion.com` |
| Netlify | `netlify` | `api.netlify.com` |
| Notion | `notion` | `api.notion.com` |
| OneDrive | `one-drive` | `graph.microsoft.com` |
| Outlook | `outlook` | `graph.microsoft.com` |
| PDF.co | `pdf-co` | `api.pdf.co` |
| Pipedrive | `pipedrive` | `api.pipedrive.com` |
| Podio | `podio` | `api.podio.com` |
| QuickBooks | `quickbooks` | `quickbooks.api.intuit.com` |
| Quo | `quo` | `api.openphone.com` |
| Salesforce | `salesforce` | `{instance}.salesforce.com` |
| SignNow | `signnow` | `api.signnow.com` |
| Slack | `slack` | `slack.com` |
| Snapchat | `snapchat` | `adsapi.snapchat.com` |
| Square | `squareup` | `connect.squareup.com` |
| Stripe | `stripe` | `api.stripe.com` |
| Systeme.io | `systeme` | `api.systeme.io` |
| Tally | `tally` | `api.tally.so` |
| Telegram | `telegram` | `api.telegram.org` |
| TickTick | `ticktick` | `api.ticktick.com` |
| Todoist | `todoist` | `api.todoist.com` |
| Toggl Track | `toggl-track` | `api.track.toggl.com` |
| Trello | `trello` | `api.trello.com` |
| Twilio | `twilio` | `api.twilio.com` |
| Typeform | `typeform` | `api.typeform.com` |
| Vimeo | `vimeo` | `api.vimeo.com` |
| WhatsApp Business | `whatsapp-business` | `graph.facebook.com` |
| WooCommerce | `woocommerce` | `{store-url}/wp-json/wc/v3` |
| WordPress.com | `wordpress` | `public-api.wordpress.com` |
| Xero | `xero` | `api.xero.com` |
| YouTube | `youtube` | `www.googleapis.com` |
| Zoho Bigin | `zoho-bigin` | `www.zohoapis.com` |
| Zoho Bookings | `zoho-bookings` | `www.zohoapis.com` |
| Zoho Books | `zoho-books` | `www.zohoapis.com` |
| Zoho Calendar | `zoho-calendar` | `calendar.zoho.com` |
| Zoho CRM | `zoho-crm` | `www.zohoapis.com` |
| Zoho Inventory | `zoho-inventory` | `www.zohoapis.com` |
| Zoho Mail | `zoho-mail` | `mail.zoho.com` |
| Zoho People | `zoho-people` | `people.zoho.com` |
| Zoho Recruit | `zoho-recruit` | `recruit.zoho.com` |

## References (per-service routing and paths)

This skill includes a **references/** folder copied from [maton-ai/api-gateway-skill/references](https://github.com/maton-ai/api-gateway-skill/tree/main/references). See **references/** for detailed routing guides per provider. Each file (e.g. `references/slack.md`, `references/hubspot.md`) describes API paths, examples, and routing for that service.

- ActiveCampaign – Contacts, deals, tags, lists, automations, campaigns
- Acuity Scheduling – Appointments, calendars, clients, availability
- Airtable – Records, bases, tables
- Apollo – People search, enrichment, contacts
- Asana – Tasks, projects, workspaces, webhooks
- Attio – People, companies, records, tasks
- Basecamp – Projects, to-dos, messages, schedules, documents
- beehiiv – Publications, subscriptions, posts, custom fields
- Box – Files, folders, collaborations, shared links
- Brevo – Contacts, email campaigns, transactional emails, templates
- Calendly – Event types, scheduled events, availability, webhooks
- Cal.com – Event types, bookings, schedules, availability slots, webhooks
- CallRail – Calls, trackers, companies, tags, analytics
- Chargebee – Subscriptions, customers, invoices
- ClickFunnels – Contacts, products, orders, courses, webhooks
- ClickSend – SMS, MMS, voice messages, contacts, lists
- ClickUp – Tasks, lists, folders, spaces, webhooks
- Clockify – Time tracking, projects, clients, tasks, workspaces
- Coda – Docs, pages, tables, rows, formulas, controls
- Confluence – Pages, spaces, blogposts, comments, attachments
- CompanyCam – Projects, photos, users, tags, groups, documents
- Cognito Forms – Forms, entries, documents, files
- Constant Contact – Contacts, email campaigns, lists, segments
- Dropbox – Files, folders, search, metadata, revisions, tags
- Dropbox Business – Team members, groups, team folders, devices, audit logs
- ElevenLabs – Text-to-speech, voice cloning, sound effects, audio processing
- Eventbrite – Events, venues, tickets, orders, attendees
- Fathom – Meeting recordings, transcripts, summaries, webhooks
- Firebase – Projects, web apps, Android apps, iOS apps, configurations
- Fireflies – Meeting transcripts, summaries, AskFred AI, channels
- GetResponse – Campaigns, contacts, newsletters, autoresponders, tags, segments
- GitHub – Repositories, issues, pull requests, commits
- Gumroad – Products, sales, subscribers, licenses, webhooks
- Google Ads – Campaigns, ad groups, GAQL queries
- Google Analytics Admin – Reports, dimensions, metrics
- Google Analytics Data – Reports, dimensions, metrics
- Google BigQuery – Datasets, tables, jobs, SQL queries
- Google Calendar – Events, calendars, free/busy
- Google Classroom – Courses, coursework, students, teachers, announcements
- Google Contacts – Contacts, contact groups, people search
- Google Docs – Document creation, batch updates
- Google Drive – Files, folders, permissions
- Google Forms – Forms, questions, responses
- Gmail – Messages, threads, labels
- Google Meet – Spaces, conference records, participants
- Google Merchant – Products, inventories, promotions, reports
- Google Play – In-app products, subscriptions, reviews
- Google Search Console – Search analytics, sitemaps
- Google Sheets – Values, ranges, formatting
- Google Slides – Presentations, slides, formatting
- Google Tasks – Task lists, tasks, subtasks
- Google Workspace Admin – Users, groups, org units, domains, roles
- HubSpot – Contacts, companies, deals
- Instantly – Campaigns, leads, accounts, email outreach
- Jira – Issues, projects, JQL queries
- Jobber – Clients, jobs, invoices, quotes (GraphQL)
- JotForm – Forms, submissions, webhooks
- Keap – Contacts, companies, tags, tasks, opportunities, campaigns
- Kit – Subscribers, tags, forms, sequences, broadcasts
- Klaviyo – Profiles, lists, campaigns, flows, events
- Lemlist – Campaigns, leads, activities, schedules, unsubscribes
- Linear – Issues, projects, teams, cycles (GraphQL)
- LinkedIn – Profile, posts, shares, media uploads
- Mailchimp – Audiences, campaigns, templates, automations
- MailerLite – Subscribers, groups, campaigns, automations, forms
- Mailgun – Email sending, domains, routes, templates, mailing lists, suppressions
- ManyChat – Subscribers, tags, flows, messaging
- Microsoft Excel – Workbooks, worksheets, ranges, tables, charts
- Microsoft Teams – Teams, channels, messages, members, chats
- Microsoft To Do – Task lists, tasks, checklist items, linked resources
- Monday.com – Boards, items, columns, groups (GraphQL)
- Motion – Tasks, projects, workspaces, schedules
- Netlify – Sites, deploys, builds, DNS, environment variables
- Notion – Pages, databases, blocks
- OneDrive – Files, folders, drives, sharing
- Outlook – Mail, calendar, contacts
- PDF.co – PDF conversion, merge, split, edit, text extraction, barcodes
- Pipedrive – Deals, persons, organizations, activities
- Podio – Organizations, workspaces, apps, items, tasks, comments
- QuickBooks – Customers, invoices, reports
- Quo – Calls, messages, contacts, conversations, webhooks
- Salesforce – SOQL, sObjects, CRUD
- SignNow – Documents, templates, invites, e-signatures
- SendGrid – Email sending, contacts, templates, suppressions, statistics
- Slack – Messages, channels, users
- Snapchat – Ad accounts, campaigns, ad squads, ads, creatives, audiences
- Square – Payments, customers, orders, catalog, inventory, invoices
- Stripe – Customers, subscriptions, payments
- Systeme.io – Contacts, tags, courses, communities, webhooks
- Tally – Forms, submissions, workspaces, webhooks
- Telegram – Messages, chats, bots, updates, polls
- TickTick – Tasks, projects, task lists
- Todoist – Tasks, projects, sections, labels, comments
- Toggl Track – Time entries, projects, clients, tags, workspaces
- Trello – Boards, lists, cards, checklists
- Twilio – SMS, voice calls, phone numbers, messaging
- Typeform – Forms, responses, insights
- Vimeo – Videos, folders, albums, comments, likes
- WhatsApp Business – Messages, templates, media
- WooCommerce – Products, orders, customers, coupons
- WordPress.com – Posts, pages, sites, users, settings
- Xero – Contacts, invoices, reports
- YouTube – Videos, playlists, channels, subscriptions
- Zoho Bigin – Contacts, companies, pipelines, products
- Zoho Bookings – Appointments, services, staff, workspaces
- Zoho Books – Invoices, contacts, bills, expenses
- Zoho Calendar – Calendars, events, attendees, reminders
- Zoho CRM – Leads, contacts, accounts, deals, search
- Zoho Inventory – Items, sales orders, invoices, purchase orders, bills
- Zoho Mail – Messages, folders, labels, attachments
- Zoho People – Employees, departments, designations, attendance, leave
- Zoho Recruit – Candidates, job openings, interviews, applications

## Examples (exec / Python)

### Slack – Post message

```python
import urllib.request, os, json
data = json.dumps({'channel': 'C0123456', 'text': 'Hello!'}).encode()
req = urllib.request.Request('https://gateway.maton.ai/slack/api/chat.postMessage', data=data, method='POST')
req.add_header('Authorization', f'Bearer {os.environ["MATON_API_KEY"]}')
req.add_header('Content-Type', 'application/json')
print(json.dumps(json.load(urllib.request.urlopen(req)), indent=2))
```

### HubSpot – Create contact

```python
import urllib.request, os, json
data = json.dumps({'properties': {'email': 'john@example.com', 'firstname': 'John', 'lastname': 'Doe'}}).encode()
req = urllib.request.Request('https://gateway.maton.ai/hubspot/crm/v3/objects/contacts', data=data, method='POST')
req.add_header('Authorization', f'Bearer {os.environ["MATON_API_KEY"]}')
req.add_header('Content-Type', 'application/json')
print(json.dumps(json.load(urllib.request.urlopen(req)), indent=2))
```

### Outlook – List messages (or use skill outlook-api-1.0.3)

```python
import urllib.request, os, json
req = urllib.request.Request('https://gateway.maton.ai/outlook/v1.0/me/messages?$top=10')
req.add_header('Authorization', f'Bearer {os.environ["MATON_API_KEY"]}')
print(json.dumps(json.load(urllib.request.urlopen(req)), indent=2))
```

## Error handling

| Status | Meaning |
|--------|---------|
| 400 | No connection for the requested app (connect app at maton.ai first) |
| 401 | Invalid or missing MATON_API_KEY |
| 429 | Rate limited (10 req/s per account) |
| 4xx/5xx | Passthrough from target API |

## Rate limits

- 10 requests per second per Maton account; target API limits also apply.

## Tips

1. Use each service’s official API docs for paths and parameters.
2. Custom headers (except Host/Authorization) are forwarded to the target API.
3. Query parameters are passed through.
4. All HTTP methods: GET, POST, PUT, PATCH, DELETE.

## Links

- [Maton API Gateway (OpenClaw skill)](https://github.com/maton-ai/api-gateway-skill) – upstream repo
- [References (per-service routing)](https://github.com/maton-ai/api-gateway-skill/tree/main/references) – upstream reference docs; copied into this skill’s `references/` folder
- [Maton](https://www.maton.ai/) – sign up, connections, settings
- [Maton API Reference](https://www.maton.ai/docs/api-reference)
- [Maton Community](https://discord.com/invite/dBfFAcefs2)
- [Maton Support](mailto:support@maton.ai)
- HomeClaw Outlook-only skill: `skills/outlook-api-1.0.3` (same gateway, app=`outlook`)
