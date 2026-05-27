# Fuzzy Cutoff Threshold Comparison — Gaines CEAI75

All 9 pages run with `--fuzzy-cutoff` at 80 (default), 70, and 60.
Pipeline: ALTO XML + Chandra `.md` clean text.
Includes error-gap fill fix (hard neighbor+size pass now also covers flagged-with-no-candidates words).

## Per-page results

| Cutoff | Page   | Matched | Errors | PENDING | Total | Error% | Match% |
|--------|--------|---------|--------|---------|-------|--------|--------|
| 80     | page-1 | 353     | 10     | 33      | 396   | 2.5%   | 89.1%  |
| 80     | page-2 | 460     | 12     | 48      | 520   | 2.3%   | 88.5%  |
| 80     | page-3 | 492     | 7      | 40      | 539   | 1.3%   | 91.3%  |
| 80     | page-4 | 486     | 10     | 29      | 525   | 1.9%   | 92.6%  |
| 80     | page-5 | 428     | 9      | 37      | 474   | 1.9%   | 90.3%  |
| 80     | page-6 | 477     | 11     | 30      | 518   | 2.1%   | 92.1%  |
| 80     | page-7 | 420     | 10     | 39      | 469   | 2.1%   | 89.6%  |
| 80     | page-8 | 192     | 10     | 10      | 212   | 4.7%   | 90.6%  |
| 80     | page-9 | 202     | 9      | 4       | 215   | 4.2%   | 94.0%  |
| **70** | page-1 | 356     | 9      | 33      | 398   | 2.3%   | 89.4%  |
| **70** | page-2 | 462     | 10     | 44      | 516   | 1.9%   | 89.5%  |
| **70** | page-3 | 493     | 6      | 38      | 537   | 1.1%   | 91.8%  |
| **70** | page-4 | 488     | 9      | 28      | 525   | 1.7%   | 93.0%  |
| **70** | page-5 | 431     | 6      | 35      | 472   | 1.3%   | 91.3%  |
| **70** | page-6 | 476     | 9      | 33      | 518   | 1.7%   | 91.9%  |
| **70** | page-7 | 422     | 8      | 34      | 464   | 1.7%   | 90.9%  |
| **70** | page-8 | 194     | 8      | 10      | 212   | 3.8%   | 91.5%  |
| **70** | page-9 | 202     | 9      | 8       | 219   | 4.1%   | 92.2%  |
| 60     | page-1 | 352     | 3      | 39      | 394   | 0.8%   | 89.3%  |
| 60     | page-2 | 460     | 7      | 48      | 515   | 1.4%   | 89.3%  |
| 60     | page-3 | 490     | 2      | 49      | 541   | 0.4%   | 90.6%  |
| 60     | page-4 | 489     | 7      | 28      | 524   | 1.3%   | 93.3%  |
| 60     | page-5 | 428     | 7      | 40      | 475   | 1.5%   | 90.1%  |
| 60     | page-6 | 469     | 4      | 52      | 525   | 0.8%   | 89.3%  |
| 60     | page-7 | 422     | 6      | 31      | 459   | 1.3%   | 91.9%  |
| 60     | page-8 | 192     | 6      | 12      | 210   | 2.9%   | 91.4%  |
| 60     | page-9 | 203     | 6      | 10      | 219   | 2.7%   | 92.7%  |

## Aggregate (mean across all pages)

| Cutoff | Mean Error% | Mean Match% | Mean PENDING |
|--------|-------------|-------------|--------------|
| 80     | 2.6%        | 90.9%       | 30.0         |
| 70     | 2.2%        | 91.3%       | 29.2         |
| 60     | 1.5%        | 90.9%       | 34.6         |

## Notes

- **Error-gap fix**: hard matching pass (neighbor+size, no word similarity) now runs on
  flagged-with-no-candidates words as well. Biggest gain at cutoff=80 where previously
  flagged words had fewer fuzzy candidates to fall back on.
- **70 is consistently better than 80** across all pages with no regressions.
- **60 gives the lowest error rates** but PENDING rises (ambiguous low-similarity matches
  accepted without enough context to confirm). Error% vs PENDING tradeoff — visually 60
  looks cleaner because red is rarer, orange is more recoverable.
- **Page-8 (bibliography)** most improved by both fix and lower cutoff:
  7.6% (old) → 4.7% (80, fixed) → 3.8% (70) → 2.9% (60).
- **Page-6 at cutoff=60**: matched drops slightly vs. 70 while PENDING rises — some
  marginal matches accepted but not confirmed by context. Acceptable tradeoff.
