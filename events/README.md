Event files look like:
{"name": "Company X IPO (Mar 2026)", "sources": ["https://...rhp.pdf", "https://...news"]}

If a site blocks downloads, save the file yourself and keep citing the public link:
{"name": "...", "sources": [{"url": "https://public/link.pdf", "file": "C:/saved/link.pdf"}]}

saved/ holds the two copies I saved by hand, because NSE and Moneycontrol refuse scripts:
  rba_nse_20jan2026.pdf        NSE press release, 20 Jan 2026 (public exchange filing)
  astrotalk_moneycontrol.html  Moneycontrol article, 12 Aug 2026 (saved from the browser)
They are in the submission zip so RBA and Astrotalk can be re-run, but kept out of Git
(.gitignore). Reports always cite the public URL, never the local copy.

Sources starting with "TODO" are skipped (and listed in the report's run notes).

Nothing in the code reads the event name to decide what to do, so any new event works.
