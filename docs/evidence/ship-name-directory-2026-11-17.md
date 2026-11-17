# Ship-name directory release verification (2026-11-17)

PR11 merged to `922dc96636ee08021224a76b40a62874cb23c733` after explicit user approval to mark ready, merge and deploy. Existing Free production deployment `dep-dbu5nc3l550s73a11pp0` was observed Live. No paid services or provider credentials added.

232 Django tests and two Node UI suites passed. Preview verified XIN YANG PU -> Xin Pu Yang/9320477; EVER GIVEN -> distinct 2018/9811000 and 1986/8320901 identities plus a fuzzy Ever Greet match; MAERSK ALABAMA -> MV Tygra/9164263; QUEEN MARY 2 ->9241061 plus another candidate. Invented-name empty results, short-query rejection, explicit choice, stale selection clearing and repeat search passed. Production independently verified EVER GIVEN candidates and the selected external URL ending `?imo=9811000`.

This is an incomplete Wikidata CC0 identity directory, not live vessel tracking. Names/aliases can be stale or ambiguous. No candidate is auto-selected, no position is returned, and external VesselFinder links do not guarantee current data. The API request sends only the submitted ship name, never the cargo form.

The initial preview returned Wikidata's `maxlag` error. Official https://www.mediawiki.org/wiki/Manual:Maxlag_parameter explicitly permits interactive user-waiting tasks to omit that optional parameter. Only the POST user-lookup path now does so; default noninteractive calls retain maxlag=5. Bounded cache, request count, fixed host, no redirects/retries, cooldowns and HTTP429/503 handling remain. Logs include allowlisted diagnostic categories, not query/body/error text.

UN/LOCODE data was not imported: a CC BY footer conflicts with the official site's restrictive terms, with no verified data-specific override. Open Waters raw position redistribution and VesselFinder embed usage scope are not resolved by this release; these providers remain disabled.
