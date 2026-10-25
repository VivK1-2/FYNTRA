# Evaluation: the 31-question test

FYNTRA is measured with a fixed set of 31 questions, stored in [`backend/eval/questions.json`](../backend/eval/questions.json)
and run by [`backend/scripts/eval_qa.py`](../backend/scripts/eval_qa.py).

## The questions

| Type | Count | What is asked |
|---|---|---|
| Figure lookup | 19 | A specific number in a specific report |
| Narrative | 4 | What the report says about a topic |
| Unanswerable | 5 | Things no annual report contains (the correct result is a refusal) |
| Comparison | 3 | One question put to two companies at once |

All questions use the fiscal-2024 Form 10-K filings of Apple (filed 2024-11-01), Microsoft (2024-07-30) and
Tesla (2025-01-29). Each question is pinned to one filing, so results do not change when a newer report appears.

### Samples

| Type | Question | Counts as correct when |
|---|---|---|
| Figure | What were Apple's total net sales in fiscal 2024? | `391,035` (USD millions) appears in the answer, with a citation |
| Figure | How many full-time equivalent employees did Apple have at the end of fiscal 2024? | `164,000`, with a citation |
| Figure | What was Microsoft's diluted earnings per share in fiscal year 2024? | `11.80`, with a citation |
| Figure | How many vehicles did Tesla deliver in 2024? | `1,789,226`, with a citation |
| Narrative | What are the main supply chain risks Apple describes? | Mentions suppliers, supply or components, with a citation |
| Narrative | What does Microsoft say about artificial intelligence? | Mentions AI, with a citation |
| Unanswerable | What will Apple's total net sales be in fiscal 2030? | The system refuses (`insufficient_evidence`) |
| Unanswerable | What is the home address of Tesla's chief executive? | The system refuses |
| Comparison | How many people does the company employ? (Apple and Microsoft) | `164,000` for Apple and `228,000` for Microsoft, each cited |
| Comparison | What was net income for the year? (Apple and Microsoft) | `93,736` for Apple and `88,136` for Microsoft, each cited |

## How it is run

1. **Pinned reports.** The script finds each filing by its filing date and, with `--prepare`, downloads and indexes it first.
2. **The same path as a user.** Each question is sent to the running backend through `POST /company/{ticker}/ask`
   (or `POST /compare/ask` for comparison questions). Retrieval, the model call and the three verification checks
   are all part of what is tested.
3. **Scoring in code** ([`app/services/evalkit.py`](../backend/app/services/evalkit.py)):
   - Figure and comparison questions pass when the expected figure appears in the answer (with or without thousands
     separators) **and** the answer has at least one citation.
   - Narrative questions pass when one of the expected key words appears and the answer is cited.
   - Unanswerable questions pass only when the system refuses.
4. **Pacing and record.** A two-second pause between questions keeps the run inside the rate limit. Each run writes a dated
   report to `backend/eval/results/` with the measures and the failed questions.

```bash
cd backend
python scripts/eval_qa.py --prepare   # first time: downloads and indexes the three reports (slow)
python scripts/eval_qa.py             # later runs
```

## Result (run with GPT-6 Luna)

| Measure | Result |
|---|---|
| Figure accuracy (number correct and cited) | 19 / 19 |
| Narrative questions answered with citations | 3 / 4 |
| Unanswerable questions correctly refused | 5 / 5 |
| Comparison questions answered for both companies | 3 / 3 |
| Answers with at least one verified citation | 100% |
| Median response time | 4.5 s |

The set is small (31 questions on three companies), so this is a check of behaviour and not a statistical benchmark.
The model is set in `backend/.env`; run the script again after any model change so the numbers belong to the model in use.
