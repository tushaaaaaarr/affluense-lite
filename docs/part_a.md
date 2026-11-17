# Part A: Reverse-engineering Affluense (from public material only)

Labels: **O** = Observed (they say it, link given), **I** = Inferred (follows from an O, I say
which), **G** = Guess. All "O" items are the company's own marketing, so "they say X" is not
"X is true".

## 1. The pipeline (my best picture)

```
SOURCES            DETECT              LINK TO PEOPLE        ENRICH             SERVE
exchange/SEBI  ->  event classifier -> match names to   ->  360° profile  ->  live feed
filings, MCA,      (code + LLM for     directors /           net-worth tier     + alert
news, ROC          messy news)         shareholders          (LLM summarises)   + network graph
   |                   |                    |                     |                 |
  code              LLM+code             code+LLM(ambig)       LLM + rules      code
                                              \_______ human QA on some profiles (G) _______/
```

| # | Claim | Label | Basis |
|---|---|---|---|
| 1 | Product tracks IPOs, ESOPs, M&A as events | O | [softwarefinder listing](https://softwarefinder.com/sales-tools/affluense-ai), [affluense.ai/hni-database-india](https://www.affluense.ai/hni-database-india) |
| 2 | Sources include MCA and SEBI public filings; profiles appear "typically within 24 to 48 hours" of the event | O | [their blog](https://www.affluense.ai/blog/best-hni-lead-generation-software-india) |
| 3 | Also claims GST, EPFO, property records, news | O (claim) | [their blog](https://www.affluense.ai/blog/best-tool-to-find-hnis-in-india). I doubt GST/EPFO are bulk-accessible: G |
| 4 | Events are linked to "beneficiaries" and turned into research profiles | O | [Hubbis interview](https://hubbis.com/article/making-the-invisible-visible-affluense-ai-s-sumit-sahu-on-data-client-acquisition-and-institutional-intelligence) |
| 5 | Network graph is built from the **client's own and colleagues' contacts** | O | [their blog](https://www.affluense.ai/blog/how-affluense-ai-identifies-hni-prospects) |
| 6 | Profiles are "verified by AI" before reaching the RM | O | [their page](https://affluense.ai/prospecting-tools-for-private-banks-india) |
| 7 | Profile includes mobile/email "cross-checked from multiple sources" | O | [their blog](https://www.affluense.ai/blog/wealthx-alternatives-for-indian-wealth-managers) |
| 8 | Filings are parsed by an LLM into structured events | I | from 2 (24-48h across many filing formats is hard with only rules) |
| 9 | The 24-48h gap is partly a human check | G | speed claim + "verified" claim together; no evidence of humans |
| 10 | Net worth is a modelled estimate (holdings x price + guesses), not a fact | I | from 1 + tiers; no public data gives true net worth |
| 11 | Name matching uses fuzzy rules + director IDs (DIN) from MCA | G | DIN is the only stable ID in public Indian data, so it's the natural key |
| 12 | Contact details come from data brokers, not public filings | G | filings don't contain personal phone numbers |
| 13 | CRM upload is matched against their database to flag "hidden" HNIs | O | [their page](https://affluense.ai/prospecting-tools-for-private-banks-india) |

## 2. Three hardest problems

1. **Right person.** "Rajesh Sharma" is thousands of people. A filing gives a name and maybe a
   DIN or PAN fragment; a news story gives a first name and a company. Wrong match = an RM calls
   the wrong person with a wrong story. *My guess at their fix:* match on DIN/company+role, only
   auto-link when two signals agree, send the rest to a human queue (G).
2. **How much, and when.** Filings say "up to N shares at a price band", not "X rupees paid on
   date Y". ESOP payouts depend on vesting and tax. *Guess:* they publish tiers (bands), not
   numbers, which hides the uncertainty (I, from "net-worth tiers"). I would show ranges + working.
3. **Fresh and trustworthy at the same time.** 24-48h leaves no time for careful checking, and
   LLMs make confident mistakes on tables. *Guess:* extraction by LLM with schema checks, plus
   spot checks by staff (G).

## 3. The business

- **Buyer:** head of a wealth firm / private bank / distribution business. **Daily user:** RM.
  (O: "wealth managers, private bankers and financial advisors", [blog](https://www.affluense.ai/blog/how-affluense-ai-identifies-hni-prospects); "trusted by 150+ wealth managers, family offices, and private banks", [page](https://affluense.ai/hni-research-tool).)
- **What an RM does with it (I):** sees the event, reads the profile, finds a warm intro through
  the graph, calls within days with a relevant pitch (what to do with fresh liquidity).
- **Copy:** event-first feed (not a static database); warm-intro graph from the firm's own
  contacts; one-screen profile.
- **Do differently:** (a) show amount as a range with working and keep "right person?"
  confidence separate; (b) every fact links to its source; (c) no personal phone/email scraping
  (legal risk, see Part C); (d) rank by "worth calling now", not just net worth.
