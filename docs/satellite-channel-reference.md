# IPTV satellite channel reference

avtrack uses this local reference to suggest **Satellite** during CSV/Excel IPTV import preview and row review. The suggestion remains editable, including clearing it. Onboard name rules take priority; unknown channel names remain blank. Existing inventory and JSON-restored source values are unchanged.

The source suggestion catalog contains 63 entries, including a curated starter list and the Galaxy 31 names supplied by the user. It is not a measured popularity ranking or a verified lineup for any particular cruise line, ship, region, or sailing. Logo search and storage are restricted to the 22 supplied Galaxy 31 entries. Add the ship’s actual satellite channels and aliases to `static/satellite-channels.json` as needed.

Matching ignores case, punctuation, and accents and accepts trailing HD, SD, FHD, UHD, 4K, 1080p, or 720p tags. It matches a complete channel name or listed alias rather than arbitrary text containing a network name. This avoids treating names such as “CNN Training Video” as satellite feeds. Operator-edited or cleared source selections remain unchanged when the channel name is edited.

## References

- [IPTV-org channel database snapshot](https://github.com/iptv-org/database/blob/69eca3be81cf5865ce891f34c9a1897b2c4ab9ea/data/channels.csv) — canonical names, IDs, categories, and published aliases. Retrieved 2026-10-08.
- [IPTV-org database](https://github.com/iptv-org/database) — project and data schema.
- [CC0 license](https://github.com/iptv-org/database/blob/69eca3be81cf5865ce891f34c9a1897b2c4ab9ea/LICENSE) — source data license.
- [LyngSat Galaxy 31](https://www.lyngsat.com/Galaxy-31.html) — logo scope based on the channel table pasted by the user on 2026-10-08. The page was not independently retrieved. Regional feed names are recorded as aliases; the CruiseSat test card is a local catalog entry rather than an IPTV-org ID.

Additional aliases in the local catalog cover common abbreviations and former names (for example BBC World News, MSNBC, Nat Geo, FS1, and Sport24). These are application matching rules, not claims that a cruise line carries the channel. No satellite frequencies, stream URLs, or subscription details are included.

## Logos

Matched Galaxy 31 IPTV channel names display a locally bundled PNG logo immediately after the channel name, at the same height as the name’s font. The name stays visible if the logo fails to load; channels outside the supplied lineup and AV devices have no channel logo. Matching uses the same aliases and HD/SD suffix rules as import suggestions and does not depend on the saved source choice. The broader source suggestion catalog is preserved, but external logo references for channels outside the lineup have been removed. No logo requests are made to external services at runtime.

- [IPTV-org logo metadata](https://github.com/iptv-org/database/blob/69eca3be81cf5865ce891f34c9a1897b2c4ab9ea/data/logos.csv) — published logo URLs linked to channel IDs.
- [TV logo image collection](https://github.com/tv-logo/tv-logos/tree/d32e347bb7c4c640dceec23957802ad9182f58a6) — source for the 18 bundled PNG images, selected for dark backgrounds. Each image’s exact source path is recorded in the catalog. ESPN Caribbean shares the ESPN US wordmark, and ESPN 2 Caribbean shares the ESPN 2 US wordmark.

20 of the 22 supplied entries have a logo. Rai Italia Nord America and the CruiseSat test card appear without a logo. Bundled PNG storage decreased from 745,392 to 285,633 bytes (61.7%). Logos remain channel brand assets; the CC0 license applies to IPTV-org catalog metadata, not ownership of the channel logos.

## Galaxy 31 logo scope

- CBS News
- HGTV East
- Food Network East
- Travel Channel East
- Nickelodeon East
- ESPNU
- ESPN US
- ESPN 2 US
- SEC Network
- CruiseSat test card (no logo)
- Sky News International
- Sky Sports News
- ESPN Caribbean
- ESPN 2 Caribbean
- Rai Italia Nord America (no logo)
- RTL Deutschland
- TVE Internacional América
- National Geographic East
- National Geographic Wild
- MS Now
- CNBC US
- MLB Network

## Included channels

- ESPN
- ESPN 2
- ESPN Caribbean
- ESPNU
- ESPN Deportes
- Sport 24
- Sport 24 Extra
- Eurosport 1
- Eurosport 2
- Sky Sports News
- Fox Sports 1
- Fox Sports 2
- CNN
- CNN International
- BBC News
- Sky News
- CNBC
- MS NOW
- Fox News Channel
- Bloomberg TV
- Euronews English
- France 24
- DW
- NHK World-Japan
- CGTN
- Discovery Channel
- National Geographic
- National Geographic Wild
- Animal Planet
- History
- TLC
- HGTV
- Food Network
- Travel Channel
- Cartoon Network
- Boomerang
- Nickelodeon
- Nick Jr.
- Disney Channel
- TNT
- TBS
- USA Network
- Comedy Central
- MTV
- VH1
- BBC Brit
- BBC Earth
- TV5Monde Europe
- Rai Italia
- TVE Internacional America
- Telemundo
- Univision
- CNA
- ITV1
- ITV2
- ITV3
- ITV4
- CBS News 24/7 (CBS News)
- SEC Network
- CruiseSat test card
- ESPN 2 Caribbean
- RTL (RTL Deutschland)
- MLB Network
