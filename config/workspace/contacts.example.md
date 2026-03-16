# Contacts for send_email

Copy this file to **share/contacts.md** in your HomeClaw sandbox so the send_email flow can resolve names (e.g. "send to John") to email addresses.

**Format:** Each contact is one line: **Name** — `email@example.com` (optional note).  
Use sections and blank lines as you like; the assistant matches the user’s wording to a name, then uses the email on that line.

---

## Work

- **Alice Chen** — alice.chen@company.com (team lead)
- **Bob Zhang** — bob@company.com
- **John Smith** — john.smith@company.com

## Family & friends

- **Emily** — emily@example.com
- **Mom** — mom@gmail.com
- **Dad** — dad@outlook.com

## Other

- **Support** — support@service.com (customer support)
- **HR** — hr@company.com

---

**Tips:**
- Use a clear display name so "send to Emily" or "email Mom" matches.
- One email per line; multiple recipients can be chosen by the user in the request.
- You can use plain lines without bullets, e.g. `John — john@example.com`, if you prefer.
