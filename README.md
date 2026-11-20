# Transactofix

Website and free transaction matcher for Transactofix (transactofix.com).

- `index.html` - business website (services, how it works, about, contact)
- `app.html` - transaction matcher: compare a bank statement CSV with a ledger CSV and list matched pairs, items only in the bank, items only in the ledger, and possible duplicates. Runs entirely in the browser; no data is uploaded.
- `styles.css` - shared styles

## Hosting

Static site, no build step. Deployed on Cloudflare Pages:
- Framework preset: None
- Build command: (leave empty)
- Build output directory: `/`
