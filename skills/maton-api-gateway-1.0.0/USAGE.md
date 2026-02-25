# How to use the Maton API Gateway skill (natural language)

You use this skill by **asking in plain language**. HomeClaw will use one Maton API token and the service you mention to call the right API. You don’t need to know URLs or paths—just say what you want.

**Before using a service:** Get your API key at [maton.ai/settings](https://www.maton.ai/settings) and **connect each app** (Slack, Outlook, etc.) once at [maton.ai](https://www.maton.ai/) (Connections). After that, you can ask for anything that service supports.

---

## Example things you can say (by service)

Use these as inspiration; you can rephrase in your own words.

### Slack
- “Send a Slack message to #general: Hello team”
- “Post to Slack channel #engineering: Deployment is done”
- “List my Slack channels”
- “What are the last 10 messages in #random?”
- “Add a thumbs-up reaction to that Slack message”

### Outlook / Microsoft 365
- “List my last 10 Outlook emails”
- “Show unread emails in Outlook”
- “Send an email from Outlook to john@example.com with subject Hello”
- “What’s on my Outlook calendar today?”
- “Create an Outlook calendar event tomorrow at 2pm: Team standup”
- “List my Outlook contacts”

### Gmail (Google Mail)
- “List my last 10 Gmail messages”
- “Search Gmail for emails from support@”
- “Send a Gmail to alice@example.com: Meeting tomorrow”
- “What are my Gmail labels?”

### HubSpot
- “Create a HubSpot contact: John Doe, john@example.com”
- “List my HubSpot contacts”
- “Search HubSpot for contacts at acme.com”
- “Create a deal in HubSpot: Acme deal, $5000”
- “List my HubSpot companies”

### Notion
- “List my Notion databases”
- “Query my Notion database [name] for tasks due this week”
- “Create a page in Notion: Meeting notes 2024-01-15”
- “Search Notion for pages about roadmap”

### Google Calendar
- “What’s on my Google Calendar today?”
- “Create a Google Calendar event next Monday 10am: 1:1 with Sam”
- “List my Google Calendar calendars”

### Google Sheets
- “Read the first 10 rows from my Google Sheet [name or ID]”
- “Append a row to my Google Sheet: col1, col2, col3”
- “What’s in range A1:B5 of spreadsheet [id]?”

### Airtable
- “List tables in my Airtable base [id]”
- “List records from Airtable table [name]”
- “Create an Airtable record in [table]: …”

### Salesforce
- “Run a Salesforce SOQL query: SELECT Id, Name FROM Contact LIMIT 10”
- “Create a Salesforce contact: …”
- “List my Salesforce opportunities”

### Stripe
- “List my Stripe customers”
- “Create a Stripe customer: email@example.com”
- “List recent Stripe payments”

### Calendly
- “List my Calendly event types”
- “What are my upcoming Calendly events?”
- “Show my Calendly availability”

### GitHub
- “List my GitHub repos”
- “Create a GitHub issue in [repo]: Bug in login”
- “List open pull requests in [repo]”

### Trello
- “List my Trello boards”
- “List cards on Trello board [name]”
- “Create a Trello card in list [name]: New task”

### Jira
- “List Jira issues in project [key]”
- “Create a Jira issue: Summary, project X”
- “Search Jira for issues assigned to me”

### OneDrive
- “List files in my OneDrive root”
- “Upload a file to OneDrive”
- “Get a OneDrive share link for [file]”

### Other services (100+ total)

You can use the same pattern for **any** service in the Supported Services table in the skill: say what you want in natural language and mention the service name (e.g. “in Notion”, “via Slack”, “from HubSpot”). Examples for more services:

- **Twilio:** “Send an SMS via Twilio to +1234567890: Hello”
- **Mailchimp:** “List my Mailchimp audiences”, “Add a contact to Mailchimp list X”
- **Typeform:** “List my Typeform forms”, “Get responses for form [id]”
- **YouTube:** “List my YouTube uploads”, “Search my YouTube channel for …”
- **Google Drive:** “List files in my Google Drive”, “Share Google Drive file [id] with …”
- **Dropbox:** “List my Dropbox folder …”, “Upload to Dropbox …”
- **Todoist:** “List my Todoist tasks”, “Add a Todoist task: Buy milk”
- **Linear:** “List Linear issues for project X”, “Create a Linear issue: …”

---

## Tips

1. **Be specific when needed.** “Send a Slack message to #general” is clear; “list my contacts” is clearer if you say “HubSpot contacts” or “Outlook contacts” when you have several CRMs/address books.
2. **Mention the service name.** “Post to Slack …”, “Create a HubSpot contact …”, “From my Outlook …” so the assistant picks the right app.
3. **First time?** If the assistant says “no connection” or “connect the app”, go to [maton.ai](https://www.maton.ai/), add that app (e.g. Slack), complete OAuth, then try again.

For full API details per service (paths, parameters), see the skill’s **references/** folder (e.g. `references/slack.md`, `references/hubspot.md`). The assistant uses those to turn your request into the right API call.
