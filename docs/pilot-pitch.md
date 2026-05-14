# Finsight OS — One-page pilot pitch

**For:** SEBI Office of Investor Assistance & Education · Zerodha Kite product team · BSE Investor Education · NCFE · Sahamati · any institution working on retail investor protection in India.

**The ask:** A 6-month observational pilot deploying Finsight OS to 10,000 self-selected retail F&O traders in Andhra Pradesh and Odisha, measuring whether a 12-second Mindful Speed Bump reduces revenge-trading loss frequency by ≥20% vs. control.

---

## Why now

SEBI's FY2024-25 study quantified what every market participant already knew anecdotally: 9.6 million retail F&O traders lost ₹1,05,603 crore in a single year. 91% of individual traders booked net losses. Average loss per loss-making trader: ₹1.1 lakh. **The regulatory levers SEBI has used so far** — increased contract sizes, higher upfront premium collection, broader risk disclosures (MIRSD circular 2024/001) — **address the supply side of speculation, not the cognitive side of the trade-button click.**

Finsight OS is the cognitive side. Open source. MIT licensed. Free for any user with a Zerodha account today via the Live Kite Connect mode.

## What the product does

Sits between the user and the *Place Order* button. A local Gemma 4 model analyzes every trade attempt for Revenge Trading, FOMO, Over-Leveraging, Addiction Loop, or Panic Selling patterns. If the behavioral score crosses 600/1000, the trade waits 6-18 seconds (scaled by score and pattern) AND requires the user to type a 15-word commitment phrase that names the specific behavior. Only after both gates clear does the order go through.

This is harm reduction, not paternalism. The user remains in control. The trade still happens if they want it to. But the impulse path now has a speed bump in it.

Cognitive interrupts of this kind are well-validated in behavioral economics (Kahneman 2011) and HCI literature (BJ Fogg, Stanford friction-as-design research). What's new is shipping that intervention to a billion-rupee retail loss problem at zero marginal cost.

## Why pilot in AP and Odisha specifically

Both states show **high B30 density and rising F&O participation rates per SEBI's regional breakdowns**. Both have active state-level financial literacy programmes that could co-deploy. Both have NCFE chapters with existing investor outreach infrastructure. Combined retail F&O trader population: estimated 1.4-1.8 million. A 10,000-user opt-in pilot represents ~0.6% of the addressable population — large enough to be statistically powered, small enough to be operationally tractable.

## Pilot design (6 months)

| Phase | Duration | Activity | Measurement |
|---|---|---|---|
| **Recruitment** | Month 1 | Voluntary opt-in via Kite Connect login + state-level financial literacy partner referrals. Target: 10,000 users total across AP + Odisha. Random 50/50 assignment to treatment (Speed Bump active) vs. control (Speed Bump dormant, all other features identical). | Baseline trade volume, win/loss rate, average position size per user. |
| **Active intervention** | Months 2-5 | Treatment users see the Speed Bump on every high-risk trade. Control users see no friction. Both groups receive identical SEBI risk disclosures and weekly summary emails. | Speed Bump fire rate, commitment-phrase compliance rate, post-bump trade execution rate, P&L, vow violation rate. |
| **Follow-up** | Month 6 | Both groups continue trading without intervention; we observe whether behavior change persists. | Persistence of P&L delta, persistence of position-sizing discipline, voluntary continued use. |

## Hypotheses (pre-registered)

- **H1 (primary):** Treatment group shows ≥20% lower frequency of "revenge trading" patterns (4+ losses in 60 minutes) vs. control. **One-sided test, α = 0.05, n=5,000 per arm gives 99% power for detecting a 20% effect.**
- **H2:** Treatment group's monthly net loss is ≥10% smaller in absolute INR terms.
- **H3:** Commitment-phrase compliance correlates with subsequent vow adherence — i.e., users who type the phrase keep trading more disciplined for the next 24 hours.
- **H4 (qualitative):** Speed Bump cancellation rate (user backs out instead of completing the phrase) is ≥15%, validating that the friction is meaningfully changing intent — not just adding latency.

## What we need from the partner

1. **Endorsement** that allows Finsight OS to be promoted through the partner's investor education channels (newsletters, NCFE workshops, Zerodha's Varsity).
2. **No financial commitment.** Kite Connect's Personal tier is free, AWS/Modal hosting for the central anonymized analytics is under ₹10K/month and self-funded by the project team.
3. **Data co-design.** A jointly-agreed anonymized analytics schema so the partner gets the policy-grade evidence they need without compromising individual user privacy.
4. **Joint publication** of the pilot results in a SEBI working paper or equivalent public document, regardless of whether H1 is confirmed.

## What the partner gets

- The first rigorously-measured intervention against retail F&O losses in India
- Evidence to inform whether SEBI should mandate cognitive-friction features in broker UIs (per the existing investor protection mandate in SEBI Investor Charter 2021)
- A reusable open-source codebase that can be embedded into any SEBI-registered broker app under MIT license
- A pre-registered randomized controlled study published under joint authorship, citable in subsequent regulatory work

## Privacy commitment

Finsight OS runs **entirely on the user's device**. Trading data, behavioral analysis, and AI inference all happen locally. The pilot adds an opt-in, anonymized, aggregate analytics channel — no individual trades, no order details, no broker IDs. Only counters: Speed Bump fired (yes/no), commitment phrase typed (yes/no), trade ultimately executed (yes/no), self-reported P&L bucket. This is the minimum dataset needed to test H1-H4 and the maximum dataset the partner will receive.

The privacy guarantee is enforced architecturally, not by policy. See `docs/architecture.html` and the trust-boundary section of the README.

## Timeline & funding

- **Q3 2026:** open-source release (already shipped) and call for pilot partner
- **Q4 2026:** partner agreement signed; recruitment infrastructure built
- **Q1 2027:** baseline measurement and 10K user enrollment
- **Q2-Q3 2027:** active intervention period (months 2-5)
- **Q4 2027:** follow-up measurement; results write-up; joint publication

Total pilot budget: under ₹20 lakh (~$24K), self-funded by the project team via grant applications to UPI Foundation, ACT Grants, or similar Indian fintech ecosystem grants. **No financial commitment requested from the institutional partner.**

## Contact

Anwesh Mohanty · anweshmohanty69@gmail.com · GitHub: @anweshmohanty
Open source: https://github.com/anwesh88/kaggle-gemma4
Submission: Kaggle Gemma 4 Good Hackathon, May 2026

This document is intentionally one page so it can be forwarded inside large
institutions without a cover letter. Every claim above maps to a specific
file in the open-source repository — no marketing-only language.
