Active event files are:

- `sedemac_ipo.json` — IPO with named selling shareholders.
- `browserstack_esop_buyback.json` — company announcement of a buyback benefiting employees and early investors; individuals are not named.
- `coding_ninjas_acquisition.json` — Info Edge's primary filing plus an accessible report on its acquisition of founder-held shares; individual founders are not named in the filing.
- `jio_platforms_ipo.json` — fresh-issue IPO used to test a correct no-seller result.

Each event file follows this format:
{"name": "Company X IPO (Mar 2026)", "sources": ["https://...rhp.pdf", "https://...news"]}

If a site blocks downloads, save the file yourself and keep citing the public link:
{"name": "...", "sources": [{"url": "https://public/link.pdf", "file": "C:/saved/link.pdf"}]}

`saved/` retains copies from earlier test events, because NSE and Moneycontrol refused scripts:
  rba_nse_20jan2026.pdf        NSE press release, 20 Jan 2026 (public exchange filing)
  astrotalk_moneycontrol.html  Moneycontrol article, 12 Aug 2026 (saved from the browser)
They are not the active event specs, but can still be uploaded in the UI for historical reruns.
Reports cite the public URL, never the local copy.

Sources starting with "TODO" are skipped (and listed in the report's run notes).

Nothing in the code reads the event name to decide what to do, so any new event works.
