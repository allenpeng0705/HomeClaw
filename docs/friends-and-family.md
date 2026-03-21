# Friends & Family

HomeClaw lets you create **AI friends** — different AI personalities that each have their own conversation, memory, and purpose. You can also add **family members** as users so everyone in your household shares one HomeClaw server with private conversations.

---

## What are AI friends?

Each user in HomeClaw has a **friends list** — a set of AI assistants they can talk to. Each friend has:

- **A unique personality** defined by a system prompt
- **Separate conversation history** — talking to one friend doesn't affect another
- **Isolated memory** — each friend remembers its own context
- **Its own knowledge base** — you can give each friend different reference files

The default friend is **HomeClaw** — your general-purpose assistant with full tools. But you can add more:

| Friend | Preset | What it does |
|--------|--------|-------------|
| **HomeClaw** | *(default)* | General assistant with all tools and plugins |
| **Reminder** | `reminder` | Scheduling, reminders, and time management |
| **Note** | `note` | Note-taking and organizing thoughts |
| **Cursor** | `cursor` | Open projects and run Cursor IDE agents |
| **ClaudeCode** | `claude-code` | Run Claude Code CLI tasks |
| **Trae** | `trae` | Run Trae Agent for coding tasks |

Or create a **custom friend** with any personality you imagine — a study partner, a language tutor, a fitness coach, a creative writing buddy.

---

## Add an AI friend

### From the Companion App

1. Open the **Companion App**
2. Go to the **Friends** screen
3. Tap **Add Friend**
4. Choose a **preset** (e.g. Reminder, Note) or create a **custom** friend
5. Set the friend's **name** and optionally customize the **personality** (system prompt)
6. The friend appears in your friends list — tap it to start chatting

### From config files

Edit `config/user.yml` and add friends under your user's `friends:` list:

```yaml
users:
  - name: Alice
    id: alice
    friends:
      - name: HomeClaw
      - name: Reminder
        preset: reminder
      - name: Note
        preset: note
      - name: "Study Buddy"
        preset: custom
        system_prompt: "You are a patient study partner who helps me understand difficult concepts. Use simple explanations and examples."
      - name: Cursor
        preset: cursor
```

Restart Core (or reload config) for changes to take effect.

### From the Portal

1. Open the **[Portal](portal.md)** in your browser
2. Go to **user.yml editor** (or User Management)
3. Find your user and edit the `friends:` list
4. Save and restart Core

---

## Create a custom AI friend

You can create a friend with any personality:

```yaml
- name: "Language Coach"
  preset: custom
  system_prompt: |
    You are a friendly language tutor who helps me practice Spanish.
    Speak mostly in Spanish with English translations when I'm stuck.
    Correct my grammar gently and suggest better ways to say things.
    Start each conversation by asking what I'd like to practice today.
```

The `system_prompt` defines the friend's personality and behavior. You can make friends for:

- **Learning** — language tutor, math helper, science explainer
- **Productivity** — note-taker, project planner, writing editor
- **Health** — fitness coach, meditation guide, meal planner
- **Fun** — storyteller, trivia host, debate partner
- **Work** — email drafter, meeting summarizer, code reviewer

Each friend gets its own conversation and memory, so they stay in character and remember past interactions.

---

## Set up a family network

HomeClaw supports **multi-user**: each family member gets their own identity, conversations, and memory on the same server.

### Step 1: Add family members as users

Edit `config/user.yml`:

```yaml
users:
  - name: Mom
    id: mom
    im:
      - companion_mom
      - telegram_111111111
    friends:
      - name: HomeClaw
      - name: Reminder
        preset: reminder

  - name: Dad
    id: dad
    im:
      - companion_dad
      - telegram_222222222
    friends:
      - name: HomeClaw
      - name: Note
        preset: note

  - name: Alice
    id: alice
    im:
      - companion_alice
      - telegram_333333333
    friends:
      - name: HomeClaw
      - name: "Study Buddy"
        preset: custom
        system_prompt: "You are a patient tutor who helps a student with homework."
```

### Step 2: Connect each person

Each family member can connect to HomeClaw in their own way:

- **Companion App** — Each person installs the app and sets a different **user_id** in Settings (e.g. `companion_mom`, `companion_dad`, `companion_alice`)
- **Telegram** — Everyone uses the same Telegram bot; HomeClaw identifies them by their Telegram chat ID (the `telegram_xxx` in their `im` list)
- **WebChat** — Each person enters their user_id when opening the webchat

### Step 3: Privacy

Each user's conversations are private:

- **Chat history** is stored per user — Mom can't see Alice's conversations
- **Memory** (RAG) is scoped per user — what Dad tells the AI isn't visible to others
- **Friends** are per user — Alice can have a Study Buddy that Mom doesn't see
- **Knowledge files** are per user — each person can upload their own reference documents

### Remote access for the family

Once you set up a [tunnel](remote-access.md) (Cloudflare, Pinggy, or ngrok), every family member can use HomeClaw from their phone — even away from home. Just share the tunnel URL and API key with each person, and they configure it in their Companion App.

---

## Add a user-type friend (another person)

Besides AI friends, you can also add other HomeClaw users as "friends" in the Companion App. This lets you see who else is on the system and potentially share resources, though conversations remain private.

---

## How friend folders work

Behind the scenes, HomeClaw creates a folder structure for each user and each friend:

```
homeclaw_root/
  alice/
    knowledge/        ← Alice's personal knowledge base
    output/           ← Alice's generated files
    HomeClaw/
      knowledge/      ← HomeClaw friend's knowledge (for Alice)
      output/
    Study Buddy/
      knowledge/      ← Study Buddy's knowledge (for Alice)
      output/
  dad/
    knowledge/
    output/
    HomeClaw/
      knowledge/
      output/
```

Each friend has its own `knowledge/` folder where you can place reference files. The AI will use those files (via RAG) when chatting with that friend.

---

## Tips

- **Friends not showing up?** If you edited `user.yml` by hand, restart Core. HomeClaw migrates users to its database at startup.
- **Friends from the Companion App** are created immediately — no restart needed.
- **Want to reset a friend?** Delete the friend from your friends list and re-add it. Or clear the friend's knowledge folder.
- **Preset definitions** live in `config/friend_presets.yml`. You can customize the presets' system prompts and tool access there.
- **Different friends, different tools:** Preset friends like Cursor only see coding tools, while HomeClaw (default) sees all tools. This keeps each friend focused on its purpose.
