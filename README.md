# Nova — AI Course Assistant for Telegram

Nova is a Telegram-based course assistant built for university EAP and humanities courses. Students interact with her through Telegram to ask course questions, work through readings, practice for seminars, and generate personalized quizzes. Instructors manage her entirely through Telegram — no dashboard, no separate app.

Nova is designed to be grounded, pedagogically informed, and bilingual (English/Chinese). She answers only from your course materials and never improvises.

---

## What Nova Does

**For students:**
- Answers questions about the course (policies, assignments, grading, dates) from your course website
- Runs study sessions on specific readings or video transcripts
- Asks students why they are reading something before starting — then adjusts how she helps
- Generates personalized quizzes based on what a student has been struggling with
- Reinforces the academic English skills you have taught, cumulatively across units
- Reminds students of tools and strategies you have recommended
- Responds in Chinese when students write in Chinese, and can invite Chinese thinking as a scaffold
- Encourages students to meet with you when they are stuck

**For you as instructor:**
- Upload readings, transcripts, rubrics, and skills content via Telegram at any time
- Push weekly observations that Nova weaves into her responses
- View uploaded materials and delete them if needed
- All of this happens in the same Telegram chat — Nova recognizes you by your Telegram ID

---

## How Instructor Mode Works

You and your students all message the same bot. Nova checks your Telegram user ID against the `INSTRUCTOR_TELEGRAM_ID` you set in your configuration. If it matches, you see instructor commands. If it doesn't, you get student mode.

**Student commands:** `/start` `/help` `/study` `/quiz` `/struggles` `/settings`

**Instructor commands (you only):**
| Command | What it does |
|---|---|
| `/note Your observation` | Push a weekly observation Nova weaves into responses |
| `/clearnotes` | Clear all current instructor notes |
| `/materials` | List all uploaded materials |
| `/deletematerial <id>` | Delete a material by ID |
| Send any file with a caption | Upload course content (see below) |

---

## Setup: Step by Step

### 1. Create a Telegram bot
- Open Telegram and search for **@BotFather**
- Send `/newbot` and follow the prompts
- Copy the token BotFather gives you — this is your `TELEGRAM_TOKEN`

### 2. Find your Telegram user ID
- Search for **@userinfobot** on Telegram
- Send it any message — it will reply with your numeric user ID
- This is your `INSTRUCTOR_TELEGRAM_ID`

### 3. Get an Anthropic API key
- Go to [console.anthropic.com](https://console.anthropic.com)
- Create an API key
- This is your `ANTHROPIC_API_KEY`

### 4. Set up your course website
- Nova reads your course site automatically using a headless browser
- Google Sites works well and is free
- This URL is your `GOOGLE_SITE_URL`

### 5. Configure your `.env` file
Copy `.env.example` to `.env` and fill in your values:

```
TELEGRAM_TOKEN=your_bot_token_here
ANTHROPIC_API_KEY=your_anthropic_key_here
GOOGLE_SITE_URL=https://sites.google.com/view/yourcourse/home
INSTRUCTOR_TELEGRAM_ID=your_numeric_telegram_id
COURSE_NAME=Your Course Name
INSTRUCTOR_NAME=Your Name
BOOKING_LINK=https://your-booking-link.com
```

### 6. Add your course introduction
Replace the contents of `course_intro.txt` with the text from your first-day handout or syllabus introduction. This is included in every conversation so students can ask Nova about course structure, expectations, and logistics.

### 7. Set up your units
Edit `units.json` to match your course structure. For each unit, fill in:
- `name` — the unit title students will see in the menu
- `guiding_question` — the central intellectual question for the unit
- `skill_focus` — the academic English skill practiced in this unit
- `skill_lesson` — a short ID that matches the tag you'll use when uploading skill content (e.g. `transitions`)
- `artwork` — optional featured artwork or anchor object for the unit
- `materials` — list of readings and video transcripts for the unit

### 8. Deploy to Render
- Create a new **Web Service** on [render.com](https://render.com)
- Connect your GitHub repo
- Set all the same environment variables from your `.env` in the Render dashboard
- Nova will start automatically and stay running 24/7

---

## Uploading Content via Telegram

Once Nova is running, you manage all course content through Telegram. Send any file to the bot with a caption — the caption becomes the tag Nova uses to find and use that content.

**Tagging conventions:**

| What you're uploading | Caption to use |
|---|---|
| Reading for Unit 1 | `unit1 reading1` |
| Video transcript for Unit 1 | `unit1 video1` |
| Skills module lesson on transitions | `skill transitions` |
| Assignment rubric | `midterm rubric` |
| Any other material | Any descriptive tag you choose |

**Supported file types:** PDF, Word (.docx), PowerPoint (.pptx), plain text (.txt)

**Skills content** is special: Nova accumulates skills across units. If a student is in a Unit 2 study session, Nova automatically has access to the Unit 1 skill content *and* the Unit 2 skill content — and actively reinforces both. Upload skill content with the tag `skill [lesson_id]` where `lesson_id` matches what you put in `units.json`.

---

## What Goes Where

| Configuration type | Where it lives | When to set it |
|---|---|---|
| Bot token, API key, site URL | `.env` / Render dashboard | Once, at setup |
| Course name, instructor name, booking link | `.env` / Render dashboard | Once, at setup |
| Course introduction | `course_intro.txt` | Once per course |
| Unit structure, guiding questions, skills | `units.json` | Once per course, update as needed |
| Reading and video transcripts | Upload via Telegram | As you add materials |
| Skills module content | Upload via Telegram with `skill` tag | When you teach each skill |
| Weekly instructor observations | `/note` command in Telegram | Weekly |

---

## Nova's Pedagogical Design

Nova's behavior is informed by four peer-reviewed studies in EAP pedagogy and EMI research. The full papers are in the `training/` folder.

**Key behaviors:**
- Scaffolds comprehension without replacing reading — always redirects students back to the original text
- Asks students to try making connections themselves before explaining
- Supports seminar preparation by helping students develop their own position, not just understand content
- Explains in plain language first, then introduces academic terminology
- Invites Chinese thinking as a legitimate cognitive tool, then works toward English expression
- Acknowledges frustration warmly before responding to content
- Encourages students to meet with the instructor when stuck
- Gently suggests breaks after extended sessions

**What Nova will not do:**
- Answer from outside the course materials
- Suggest external resources (except tools the instructor has explicitly recommended)
- Add unsolicited follow-up offers or filler
- Do the thinking for the student

---

## NovaBenchmark

A companion testing toolkit is available at [github.com/sarahwarf/NovaBenchmark](https://github.com/sarahwarf/NovaBenchmark). It runs six simulated student personas against your Nova deployment so you can test her behavior before students interact with her. Recommended before each new semester.

---

## License

MIT — free to use, adapt, and share. If you build on this for your own course, a note back to the original project is appreciated but not required.
