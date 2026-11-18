# What's broken

**Where it gives wrong answers (real examples from my runs, all in `backend/outputs/`)**
- **A number 1,000× too small.** SEDEMAC RHP page 111: *"…30, 000 Equity Shares … were allotted to Arvind Munde"*. The PDF text has a space inside "30,000", my number reader stopped at "30", and the report said **30 shares, ₹0.0 cr**. The AI copied the quote correctly; my code misread it. Fixed (split numbers are rejoined) with a test, but other PDF layouts can break numbers in ways I haven't seen yet.
- **An incubator ranked #1 as a person to call.** First SEDEMAC run: "Society for Innovation and Entrepreneurship" topped the call list, with "…Sanghavi HUF" (a family entity) at #5. `is_org` is a word list and didn't know "Society" or "HUF". Fixed by adding Indian legal forms, but it's still a word list: "Inspira Global" (RBA) would still look like a person.
- **Two brothers flagged as maybe the same man.** "Atul Hiralal Shah" / "Bakul Hiralal Shah" (same father's name) lost confidence (0.5→0.3) for each other. Fixed: different full first names now mean different people.
- **Still open:** a real seller is missing. "Capri Global Holdings Private Limited" is dropped because its name wasn't in the quote the model copied (a missing answer, not a wrong one). The 8 ESOP holders come from the *allotment history*; I value shares they **were given**, not shares I know they still hold. "Up to N shares" assumes 50% were sold (my number, labelled). Timing knows "offer closed on 6 Mar", not "money in the bank".

**What I tried that didn't work**
- **Keyword page picking** chose boilerplate over the seller table (page 476) of a 582-page RHP. Now share-count rows score highest.
- **Asking the model for integers** turned "₹120 crore" into 1200000000, which my own check then rejected. Now the model copies words and code converts.
- **One model call per call note:** 14 calls, 8 minutes, then Gemini's free tier (20 requests/day) ran out mid-run. Now 10 people per call: 4 calls, 20 s, $0.02.
- **A "thinking" model** (Gemini 3.5 Flash) hid most of its billed tokens from the output count, so my cost log was ~70× too low, and it cut one note off mid-sentence. I now count all tokens, treat cut-off replies as no reply, and use Flash-Lite.
- **Fetching:** Python's robots.txt reader wrongly banned a whole site; a SEBI download broke halfway; SEBI pages hide the PDF in an iframe; NSE hangs scripts (now fails in ~30 s); Moneycontrol/BSE refuse scripts (I save the file and cite the public link, rather than faking a browser).

**AI tools:** most useful for scaffolding, tests and reading 500-page filings fast. They misled me by sounding certain: a made-up model price list, the crore-to-integer design, and a model name (`gemini-2.5-flash`) that had been retired.

**With 2 more weeks (in order):** 1) table-aware PDF parsing (would fix Capri and the split numbers); 2) DIN/company as a second key for names and orgs; 3) 20 hand-checked events to measure accuracy; 4) basis-of-allotment and settlement dates for real amounts and timing; 5) CRM overlap check; 6) turn the demo UI into an authenticated RM workflow with lead assignment and evidence review.
