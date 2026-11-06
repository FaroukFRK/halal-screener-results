# Shariah screening method

Standard: AAOIFI Shariah Standard No. 21 (financial papers). This is a mechanical screen, not a fatwa.

## 1. Business activity (`shariah.business_screen`)
- **FAIL** by SIC code: banks/credit 6000–6199, brokers 6211, insurance 63xx/6411, alcohol 2082/2084/2085/5180/5182/5921,
  tobacco 21xx, asset-backed 6189.
- **FAIL** by name keyword: bank, bancorp, insurance, casino, brewing, winery, tobacco, cannabis, marijuana, lottery,
  betting, mortgage, savings, …
- **REVIEW** (mixed / depends on details): SPACs 6770, REITs 6798, hotels, restaurants, amusement/gaming, film/TV,
  ordnance, meat packing, investment/royalty firms; names with gaming, hemp, CBD, vape, capital, financial, …
- No SIC code → REVIEW.

## 2. Financial ratios (`shariah.ratio_screen`), market cap = last close × shares outstanding
| Ratio | Limit | Data |
|---|---|---|
| Interest-bearing debt / market cap | < 30% | largest of non-overlapping debt tag sets on the latest balance sheet |
| Cash + interest-bearing securities / market cap | < 30% | cash & equivalents + short-term investments |
| Interest income / (revenue + interest income) | < 5% | latest ~12-month period |

Known simplifications:
- Current market cap, not a 12/24/36-month average (Dow Jones / S&P use averages).
- Interest income is the proxy for all non-permissible income (no segment-level data in XBRL).
- Lease liabilities are not counted as debt.
- If no mapped debt tag exists but a debt-like tag appears in recent filings, debt is unknown → REVIEW.
- ADR/ADS listings → REVIEW (SEC share count is not per depositary share).
- Broad interest tags like
  `InterestAndOtherIncome` can overstate interest.
- Non-USD filers (many 20-F/40-F) get REVIEW: their debt/cash would need FX conversion.
- Purification of dividends is not calculated.
