# Staging QA Playbook

Bot: **@collective_will_dev_bot** on Telegram
Web: **https://staging.collectivewill.org**

---

## Staging Config (what matters for testing)

| Setting | Value | Meaning |
|---------|-------|---------|
| Pipeline interval | 6 min | Scheduler processes new submissions every ~6 min |
| Voting cycle duration | 1 hour | Cycle auto-closes and tallies after 1h |
| Min support for ballot | 5 | A cluster needs member_count + endorsements >= 5 to qualify |
| Auto-cycle cooldown | 0 | New cycle can open immediately after the previous one closes |
| Account age required | 0 | No waiting period after signup |
| Vote contribution required | false | Can vote without having submitted anything |
| Max submissions/day | 50 | Plenty of room for testing |
| Max vote changes/cycle | 2 | Can re-vote once (2 total submissions per cycle) |

---

## Phase 0: Prerequisites

### 0.1 Verify the environment is up

Open in browser:

- `https://staging.collectivewill.org/api/health` -- should return `{"status":"ok"}`
- `https://staging.collectivewill.org/api/health/db` -- should return `{"status":"ok"}`
- `https://staging.collectivewill.org/en` -- landing page should load

### 0.2 Account setup (if not already done)

1. Go to `https://staging.collectivewill.org/en/signup`
2. Enter your email, click "Send Verification Link"
3. Open the magic link from email (check spam if needed)
4. Copy the **linking code** from the verify page
5. Open `@collective_will_dev_bot` in Telegram, paste the linking code
6. Complete voice enrollment (read 3 short phrases aloud when prompted)
7. You should see the **main menu** with 4 buttons: Submit / Endorse / Vote / Language

If you already have an account, just open the bot and verify you see the main menu.

### 0.3 Voice verification

If your voice session has expired (30 min since last activity), the bot will ask you to read a phrase before letting you do anything. Just read it aloud and send the voice message.

---

## Phase 1: Submissions (10 prompts, 2 categories)

Tap **"Submit a concern"** (or the Farsi equivalent), wait for the prompt, then paste the message.

### Category A: Internet Freedom (6 submissions -- enough to reach threshold of 5)

**A1.**
```
The government should stop filtering internet websites and allow citizens free access to information online
```
Expected: Confirmation with AI-interpreted title, link to submission page.

**A2.**
```
Internet censorship in Iran prevents students and researchers from accessing academic resources and must be lifted
```
Expected: Same as above. Should cluster with A1.

**A3.**
```
VPN usage should be decriminalized and the filtering infrastructure should be dismantled to restore open internet
```
Expected: Confirmation. Clusters with A1-A2 under internet freedom.

**A4.**
```
Free and unfiltered internet access should be recognized as a fundamental right of every citizen
```
Expected: Confirmation. Same cluster.

**A5.**
```
Social media platforms like Instagram and Twitter should not be blocked by the authorities
```
Expected: Confirmation. Same or closely related cluster.

**A6** (Farsi -- switch language first by tapping the language button):
```
فیلترینگ اینترنت باید برداشته شود و دسترسی آزاد به اطلاعات حق هر شهروندی است
```
Translation: Internet filtering should be removed and free access to information is every citizen's right.
Expected: Confirmation in Farsi. Should cluster with A1-A5 (same policy key).

### Category B: Labor Rights (4 submissions)

**B1** (still in Farsi):
```
حقوق کارگران باید افزایش پیدا کند و حداقل دستمزد باید متناسب با تورم تنظیم شود
```
Translation: Workers' wages should increase and minimum wage should be adjusted for inflation.
Expected: Confirmation. New cluster separate from Category A.

**B2.**
```
کارگران باید حق تشکیل اتحادیه مستقل را داشته باشند بدون ترس از اخراج
```
Translation: Workers should have the right to form independent unions without fear of dismissal.
Expected: Clusters with B1.

**B3** (switch back to English):
```
Workplace safety standards in Iranian factories must be improved with mandatory inspections and accountability for violations
```
Expected: Clusters with B1-B2 under labor rights.

**B4.**
```
Workers should receive equal pay regardless of gender and employment contracts must be transparent
```
Expected: Same labor rights cluster.

### After submitting all 10

- The bot should return to the main menu after each submission
- Each confirmation should include a link like `staging.collectivewill.org/en/submission/{id}`
- Click a few of those links to verify the submission detail pages load

---

## Phase 2: Rejection Tests (2 prompts)

### Garbage input

Tap Submit, then send:
```
asdfghjkl qwerty lorem ipsum banana 12345
```
Expected: Rejection -- "Your message could not be processed as a policy proposal" (English) or equivalent in Farsi.

### Off-topic input

Tap Submit, then send:
```
I had a really great breakfast this morning, eggs and toast with coffee
```
Expected: Same rejection -- not a policy proposal.

### What to note

- Both rejections should include a contextual reason from the AI
- The bot should return to the main menu after each rejection
- Rejected submissions still count toward the daily limit

---

## Phase 3: Wait for Pipeline (6-10 minutes)

After submitting everything, the scheduler will process them within ~6 minutes.

### What to check on the web

1. **Collective Concerns** page (`/en/collective-concerns`):
   - Stats should update (submission count, cluster count)
   - "Active Concerns" section should show 2-3 clusters:
     - One for internet freedom (5-6 members)
     - One for labor rights (3-4 members)
   - Each cluster should have a ballot question in English and Farsi

2. **Evidence page** (`/en/collective-concerns/evidence`):
   - Chain status badge should be green ("Valid")
   - Filter by "Submissions" -- should see `submission_received` events
   - Filter by "Policies" -- should see `candidate_classified`, `cluster_created`, `ballot_question_generated`
   - Click "Verify Chain" -- should return valid

3. **Ops console** (`/en/ops` -- must be signed in):
   - All services green
   - Pipeline events visible in event feed
   - No errors

### If clusters don't appear after 10 minutes

- Check the ops console for pipeline errors
- The scheduler may not have run yet -- check `scheduler` service status in ops health
- Pipeline needs at least 1 pending/canonicalized submission to run the full flow

---

## Phase 4: Endorsement

Once clusters appear with ballot questions, go back to Telegram.

### Steps

1. Tap **"Endorse policies"**
2. The bot shows the first cluster with its ballot question, member count, and endorsement count
3. Tap **"Endorse 1"** to endorse the internet freedom cluster
4. The bot confirms and shows the next cluster
5. Tap **"Skip"** on the labor rights cluster (or endorse it too -- your choice)
6. After the last cluster: "All policies reviewed!"

### Expected

- Each endorsement increments the endorsement count by 1
- The internet freedom cluster should now have total_support = member_count + 1 (your endorsement)
- Refresh the cluster detail page on the web to confirm the count went up

### What to verify on the web

- Cluster detail page shows updated endorsement count
- Evidence page shows `policy_endorsed` events (filter by "Votes" category or search by cluster ID)

---

## Phase 5: Voting Cycle

### 5.1 Wait for auto-cycle opening

A voting cycle auto-opens when a cluster reaches total_support >= 5. With 6 internet-freedom submissions (member_count = 5-6) the cluster should already qualify. The scheduler checks every 60 seconds.

Check: `https://staging.collectivewill.org/en/collective-concerns/community-votes`
- A green banner should appear: "Active vote" with policy count and time remaining
- Ballot questions listed with 2-4 stance options each (but no vote counts -- "results revealed after close")

If no cycle appears after 10 minutes, check:
- Does the internet freedom cluster have options generated? (check cluster detail page)
- Is the cluster `status=open`?
- Check ops console for errors

### 5.2 Vote

1. In Telegram, tap **"Vote"**
2. Expected: cycle timing message ("Active vote -- N policies, Ends: in Xm")
3. First policy appears with a summary and 2-4 stance options (A, B, C, D buttons)
4. **Tap option A** (or whichever you prefer)
5. If there are more policies, navigate through them (tap an option or Skip)
6. After the last policy: summary of your selections, then auto-submitted
7. Expected: "Your vote has been recorded!" + link to community votes page

### 5.3 Change vote

1. Tap **"Vote"** again
2. Select **different options** this time
3. Expected: "Your vote has been recorded!" (change accepted -- 2nd of 2 allowed)

### 5.4 Vote limit test

1. Tap **"Vote"** a third time
2. Expected: Rejection -- vote change limit reached

### What to verify on the web

- `/en/collective-concerns/community-votes`: active ballot section shows policies with options
- Vote counts should be HIDDEN during the active cycle ("results revealed after close")

### 5.5 Wait for cycle close (1 hour)

After 1 hour, the scheduler auto-closes and tallies the cycle.

Check `/en/collective-concerns/community-votes` again:
- "Past Voting Results" section should appear
- Each policy shows per-option vote breakdown bars with counts and percentages
- Results are publicly visible

---

## Phase 6: Web Pages QA

Visit each page and verify it loads correctly. Check both English and Farsi.

| Page | English URL | What to check |
|------|-------------|---------------|
| Landing | `/en` | Hero, CTA buttons, "How it works", footer |
| Signup | `/en/signup` | Email form, step indicator |
| Sign In | `/en/sign-in` | Email form |
| Collective Concerns | `/en/collective-concerns` | Stats, active/archived clusters, ungrouped |
| Cluster Detail | `/en/collective-concerns/clusters/{id}` | Ballot question, member cards, audit trail link |
| Community Votes | `/en/collective-concerns/community-votes` | Active ballot or past results |
| Evidence | `/en/collective-concerns/evidence` | Chain badge, filters, pagination, expandable cards |
| Audit Bundles | `/en/collective-concerns/audit-bundles` | Bundle index (may be empty on day 1) |
| FAQ | `/en/faq` | Safety, How It Works, About sections |
| Independent Verification | `/en/independent-verification` | Verification instructions |
| My Activity | `/en/my-activity` | Submissions, votes, receipts (must be signed in) |
| Ops Console | `/en/ops` | Health, events, jobs, pipeline (must be signed in) |
| Submission Detail | `/en/submission/{id}` | Raw text, AI interpretation, evidence timeline |

### Farsi RTL check

Repeat the above with `/fa/` prefix. For each page verify:
- Text direction is RTL
- Layout is mirrored (nav on the right, cards flow right-to-left)
- No text overflow or clipping
- Farsi text renders correctly (Vazirmatn font)

---

## Phase 7: Dashboard and Receipts

Must be signed in (use `/en/sign-in` if session expired).

1. Go to `/en/my-activity`
2. **Check**: "My Submissions" lists all submissions with status badges
3. **Check**: "My Votes" shows voting history (after voting)
4. **Check**: Receipts section shows entries for `policy_endorsed` and `vote_cast` events
5. Click a receipt to see the detail page
6. **Check**: Verification status (Recorded / Published / Timestamped), entry hash visible

### Dispute test

1. In the dashboard, find a submission
2. Click "Dispute"
3. **Check**: Automated resolution processes (no human intervention)
4. **Check**: Updated classification appears if the AI re-evaluates

---

## Phase 8: Edge Cases

### Cancel mid-flow
1. Tap "Submit a concern" in the bot
2. Tap **Cancel** instead of typing a message
3. Expected: Returns to main menu, no submission recorded

### Vote with no active cycle
1. After the cycle closes (or before one opens), tap **"Vote"**
2. Expected: "There is no active vote at this time" + endorsement encouragement

### Endorse with nothing to endorse
1. If all clusters are archived (after cycle closes), tap **"Endorse policies"**
2. Expected: "No policies available for endorsement right now"

---

## Results Summary Template

Fill this in as you test:

| Module | Status | Notes |
|--------|--------|-------|
| Landing page (EN) | | |
| Landing page (FA + RTL) | | |
| Signup flow | | |
| Bot: account linking | | |
| Bot: voice enrollment | | |
| Bot: language toggle | | |
| Bot: submit (EN valid) | | |
| Bot: submit (FA valid) | | |
| Bot: submit (garbage rejection) | | |
| Bot: submit (off-topic rejection) | | |
| Pipeline: clustering | | |
| Pipeline: ballot questions | | |
| Pipeline: options generated | | |
| Bot: endorsement flow | | |
| Voting cycle auto-open | | |
| Bot: vote flow | | |
| Bot: vote change | | |
| Bot: vote limit | | |
| Cycle close + tally | | |
| Web: collective concerns | | |
| Web: cluster detail | | |
| Web: community votes | | |
| Web: evidence chain | | |
| Web: audit bundles | | |
| Web: FAQ | | |
| Web: my-activity dashboard | | |
| Web: receipts | | |
| Web: dispute | | |
| Web: ops console | | |
| Web: submission deep links | | |
| API: health endpoints | | |
| Farsi RTL across all pages | | |

---

## Quick API Checks (curl or browser)

```bash
# Health
curl https://staging.collectivewill.org/api/health
curl https://staging.collectivewill.org/api/health/db

# Stats
curl https://staging.collectivewill.org/api/analytics/stats

# Evidence chain
curl https://staging.collectivewill.org/api/analytics/evidence/verify

# Clusters
curl https://staging.collectivewill.org/api/analytics/clusters

# Active ballot
curl https://staging.collectivewill.org/api/analytics/active-ballot
```
