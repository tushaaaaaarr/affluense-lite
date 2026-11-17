# Part C: Winning the client

## 1. First meeting: questions for the Head of RMs
Each line: question -> which answer changes my design, and how.

1. **Who is a "good" prospect: minimum ₹ and which segment?** -> sets the amount floor in the ranker; a ₹5 cr floor means ignoring small ESOP holders.
2. **Think of the last 3 clients you won from a money event. What happened?** -> tells me which event types matter; if all came from IPO sellers, I drop M&A for the pilot.
3. **How do RMs hear about leads today and what do they do in the first call?** -> decides the brief format (WhatsApp text vs CRM note).
4. **What do you already have: CRM, client list, relationship data?** -> if a CRM export exists, I add a "do we already know them?" step and later a warm-intro path.
5. **Do you want people only, or also the companies/funds behind them?** -> keeps or drops the institutional list.
6. **How wrong can a lead be before RMs stop trusting it (1 in 5? 1 in 10?)** -> sets the confidence cut-off and whether low-confidence leads are hidden or shown.
7. **How fast must it be: same day, or weekly list enough?** -> weekly = batch job; same day = alerts and a higher cost.
8. **Who owns compliance sign-off and what are their rules on calling cold?** -> decides whether the pilot output is "call" or "send intro via existing contact".
9. **Where should the output land: email, Slack, CRM, Excel?** -> decides the interface; no CRM access means a CSV for the pilot.
10. **How do you measure an RM today?** -> picks the pilot metric (calls booked, meetings, AUM).

## 2. Five-minute demo script
- **0:00** One sentence: "In March, SEDEMAC Mechatronics listed and its shareholders sold about ₹1,087 crore of shares. Which of them should your team have called that week?"
- **0:30** Paste the SEBI filing link and run it. Show the screen while the steps run (fetch, extract, check): 582 pages to a call list in about 20 seconds.
- **2:00 The moment that sells it:** open one lead, click the evidence link, and the PDF page shows
  the same sentence the system quoted. Then show a person we *refused* to include because the quote
  could not be verified. "It never invents a number."
- **3:30** Show the ₹ range and its working, and confidence kept separate from the amount.
- **4:30** Show the cost line ("this whole IPO cost about two US cents; running it again costs nothing") and ask: "Which event should we run on your own list this week?"

## 3. Four-week pilot
- **Ship:** a weekly Monday list (CSV + one-page report) covering IPO sellers and buybacks/M&A; 6-8 RMs (of 40) plus 2 as a control who keep working as usual.
- **Week 1** set up with their ranking rules and compliance sign-off; **Weeks 2-4** weekly lists, 15-min feedback call per week.
- **Success measures (client outcomes):** calls connected, meetings booked, and new money in within 90 days if visible; compared with control RMs. Also "lead was the wrong person" rate (target under 10%, to be agreed). *Not* number of profiles.
- **Need from client:** 6-8 named RMs, a compliance contact, their past win examples, how they log calls.
- **What could stop it:** compliance says no to cold calls; RMs don't use the list; the data for the week's events is thin; two weeks of no usable events.

## 4. Compliance answer (short, and I'm not a lawyer)
"Using public filings to know who sold shares is generally fine, but 'publicly available' doesn't mean 'free to use for anything'. Under India's data protection law (DPDP Act, 2023) a person's name tied to their wealth is still personal data, so we need a clear purpose, limited use, and a way to honour removal requests. Calling is a separate rule set: telemarketing/DND regulations (TRAI) and SEBI's conduct rules for advisers and distributors, e.g. no pressure or misleading claims. We don't collect personal phone numbers or emails; RMs would reach people through existing relationships or business channels."
**What I'd check before saying it for real:** the current status of the DPDP Rules and which parts apply to the firm; whether the exemption for personal data a person made public applies to filings; the firm's own DND/calling policy and registration; SEBI rules for their licence type (RIA, distributor, PMS); whether a client's grievance process covers "how did you get my name"; and a lawyer's sign-off on the text.
