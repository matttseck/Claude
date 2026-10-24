# Matt & Vienna expense tracker

Single-file web app (`index.html`, no build step) for Matt and Vienna's shared expenses, hosted on
GitHub Pages from branch `claude/shared-expense-tracker-abvect` at https://matttseck.github.io/Claude/.
Develop and push on that branch only. Do not open a PR unless asked.

## Where the data lives
Firebase Realtime Database, node `expenses-data` = `{ sessions: [], expenses: [], lastUpdated }`.
The app syncs to it live on both phones. **The database URL is not stored in this repo** (rules are open,
so the URL is effectively a password). Read it from `$FIREBASE_DB_URL`, or ask the user.
The session's network policy must allow the database host, or requests get a 403 from the proxy.

`python3 tools/fb.py show` prints counts and the HKD settlement; `python3 tools/fb.py add new.json [--apply]`
merges new expenses/sessions by id (dry run by default, backs up first, aborts if the app changed the data meanwhile).
Never delete or edit existing expenses unless the user asks. Show a table of what you will add and the
resulting settlement, get the user's OK, then `--apply`.

## Data model
- Session: `{id, name, note, defaultCurrency, settled, createdAt}`. Current: `japan2610` (Japan Oct 2026, JPY), `korea2609` (Korea Sep 2026, KRW).
- Expense: `{id, sessionId, amount, currency, description, date (YYYY-MM-DD), paidBy: matt|vienna, forWhom: matt|vienna|both, splitRatio (Matt %, default 50), category, createdAt, hkd?}`.
- `hkd` = the HKD actually charged on a card statement for that expense. It is the settlement value. Without it the app
  converts at the average rate (sum hkd / sum amount per currency across all statement-backed expenses). Expenses in HKD need no `hkd`.
- Categories: groceries, dining, transport, utilities, housing, entertainment, health, shopping, subscriptions, travel, gifts, other.
- Firebase rejects `undefined`; omit absent keys.

## Conventions agreed with the user
- Do NOT record an expense when the payer and the person it is for are the same (Matt paid for Matt, Vienna for Vienna): no settlement effect.
- Record receipts item by item when who-it's-for differs; prices after coupons/discounts (spread a bill-wide coupon proportionally).
- Tax-free (refund) purchases: cost = price - 0.85 x tax (15% handling fee kept). For a 10%-tax-inclusive price that is price x (1 - 0.85/11). Korea VAT 10%, Japan 10% (8% food).
- Card slips often show only totals; ask who paid and who each item is for. Unmarked items default to "payer only" and are skipped.
- Cards: Matt = HSBC Mastercard ...1196 and BOC UnionPay ...0114. Vienna = Hana Mastercard 5427-13xx (...0932), and PayPay payments. Ownership of the card ending 8834 (Suica/LVMH) was never confirmed (treated as Matt's).
- PayPay history times are Hong Kong time (JST minus 1 hour).
- Statement HKD for one charge covering several entries: split in proportion to the foreign amounts.
- Final answer to the user is always a single HKD figure ("Vienna pays Matt HK$...") per session and overall.

## Open items (as of 2026-10-24)
- Bic Camera: statement says JPY 46,189, receipt says 47,189 (receipt kept).
- Hotels/flights (Korea HKD 2,515 + 5,670; Japan HKD 7,660.04 + 6,314), HK Express HKD 920 and the Ami dinner HKD 3,745 assumed paid by Matt, placeholder dates.
- Vienna's card statement not yet seen; her purchases use the average rate.
- Korea lines 12-13 Sep on Matt's card may be incomplete (screenshots were cut off).

## Dev notes
- Test the app with Playwright (`/opt/pw-browsers/chromium`): load `file:///.../index.html`, import JSON via `#file-input`.
- After pushing, Pages rebuilds in about a minute; browsers cache it, so use a `?v=N` query to bypass.
- Sync code lives at the bottom of `index.html` (`initSync`, `pushToRemote`); a `?sync=<db url>` link configures a new device.
