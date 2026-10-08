# avtrack fonts

Matches broadcastgab.com: Space Grotesk for headings, DM Sans for body text,
and JetBrains Mono for navigation, labels, and network values. All fonts are
served locally; no Google Fonts requests or system font installation are needed.

Variable WOFF2 files retain the original glyphs and weight ranges. PDF fonts
are static instances of the same official variable TTFs, created with FontTools.
DM Sans PDF instances use optical size 14. FontTools and Brotli are only needed
to rebuild these assets, not to run the app.

| Family | Official source | License | PDF weights |
| --- | --- | --- | --- |
| Space Grotesk | https://github.com/google/fonts/tree/main/ofl/spacegrotesk | [SIL OFL](SpaceGrotesk-OFL.txt) | Bold 700 |
| DM Sans | https://github.com/google/fonts/tree/main/ofl/dmsans | [SIL OFL](DMSans-OFL.txt) | Regular 400, Bold 700 |
| JetBrains Mono | https://github.com/google/fonts/tree/main/ofl/jetbrainsmono | [SIL OFL](JetBrainsMono-OFL.txt) | Regular 400, Medium 500 |

Source variable TTF SHA-256:

- Space Grotesk: `acad6de1fc93436f5c0f1f4137751ef04f1aea3063e7036535970ffcfbd79f72`
- DM Sans: `8cd08d97e89c24d0aa92edd2f0f4c8ee6195eee9b7c9f154865a58b02f0c1c0d`
- JetBrains Mono: `48715a42ec242c21e9f02692891e147d022299a52e48d5e413e1a942193ffeda`

Legacy Poppins files remain available for previously cached styles. They are
no longer used by the current interface or PDF generator.

## Legacy Poppins

Source: https://github.com/google/fonts/tree/main/ofl/poppins

Official TTFs converted to WOFF2 with FontTools, preserving all glyphs.
SIL Open Font License included in OFL.txt. Fonts are served locally for offline localhost use.
Legacy Regular and Bold TTF files were reconstructed from the same WOFF2
fonts with FontTools for the previous PDF generator.

Source TTF SHA-256:

- Regular: `7e65201e9b79159e2300267cc885e16c8dcef2424cdfa09a29bfb0980a94a7ba`
- Medium: `90373e7d838d32468438fc3e152dca0bdb12edcab99ea639f158790b1ba1fd05`
- SemiBold: `d3bf1bdaf0550e83da9ac0b1d1d9fe6db086835a83aa28578e609a394b9a0286`
- Bold: `983676516167748b74de6f4771fb384c664fd913acb8b471122ecacf5da5ea6c`
