Week 4 Project

**Evaluate Your Agent**

Mastering Agentic AI Certification  |  The Gen Academy

# **What this week is about**

Last week you built an agent. This week you find out if it actually works. By Friday you will have a golden dataset, real evaluation metrics, full observability through LangSmith, and a prioritized list of improvements with measured impact.

Most agents pass the demo and fail in production because no one ever evaluated them properly. "It worked when I tested it" is not an evaluation. This week separates teams that are shipping toys from teams that are shipping systems.

## **How this project works**

This is not a new project. You are piggybacking on your Week 3 agent. The four phases below run in sequence, and you will spend roughly one day on each.

| Day | Phase | What you do |
| :---: | :---- | :---- |
| **1** | **Define metrics & build golden dataset** | Translate your Week 3 success metric into measurable, automatable evaluators. Build a labeled dataset of 30 to 50 test cases covering happy paths, edge cases, and known failure modes. |
| **2** | **Instrument with LangSmith** | Wire up tracing on every LLM call and tool use. Confirm you can see end-to-end runs, intermediate steps, latency, and token cost in the LangSmith UI. |
| **3** | **Run evaluation & analyze failures** | Run your eval suite against the golden dataset in LangSmith. Cluster failures, find the dominant failure mode, and quantify the cost of each. |
| **4** | **Improve & measure delta** | Implement 3 to 4 targeted improvements. Re-run evals. Report the measured delta on each metric. Show what worked, what did not, and what you would try next. |

| Deliverable Submit an evaluation report, your golden dataset, the LangSmith project link, and a Loom walkthrough. Full requirements on page 10\. You do not have to keep your Week 3 agent; if you want to evaluate a different one (a teammate's, an open-source one), DM us by Monday EOD. |
| :---- |

# 

# **Part 1: The Evaluation Framework**

## **The Primer: Your evaluation one-liner**

Before the framework, write a single sentence that captures what you are measuring, on what, and against what bar. If you cannot say it in one line, your evaluation is not designed yet.

| I will measure \[METRIC SET\] on \[AGENT FROM WEEK 3\] using a golden dataset of \[N\] cases covering \[SCENARIO TYPES\], with \[JUDGE METHOD\]. Pass bar: \[TARGET %s \+ LATENCY \+ COST\]. I will run this in LangSmith and report the delta from \[BASELINE\] to \[POST-IMPROVEMENT\]. |
| :---- |

### **Worked example**

*I will measure red-flag recall, summary faithfulness, end-to-end task completion, and p95 latency on my Multi-Agent Deal Review Pipeline using a golden dataset of 40 historical deals (15 closed-won, 15 closed-lost, 10 edge cases) covering missing-MEDDPICC, exception-flagged, and large-deal scenarios, with LLM-as-judge for faithfulness and exact-match for red flags. Pass bar: 85% recall, 90% faithfulness, 100% completion, p95 under 2 minutes, $2 per run. I will run this in LangSmith and report the delta from baseline to post-improvement.*

| Three rules for evaluation design Metrics must map to user outcomes. "Helpfulness score" is not a metric. "Did the manager catch the red flag they would have caught manually" is. If your metric does not predict user value, it is decoration. Golden datasets are not optional. Vibes are not evaluation. You need labeled cases with known correct outputs, drawn from real usage where possible. Hand-labeled by you or a domain expert. Improvements without measured delta do not count. If you changed a prompt and feel like it got better, you did not improve anything. Run the eval before and after. Report the number. That is the work. |
| :---- |

## **The Framework**

Fill out every field in 1 to 2 sentences. The framework forces a decision at every layer of evaluation so nothing gets hand-waved.

| Field | Fill in (1 to 2 sentences max) |
| :---- | :---- |
| **Agent under test** (one line) | Which Week 3 agent (yours or a teammate's) you are evaluating. |
| **User outcome** | What the user actually needs from this agent. The thing that, if wrong, makes the agent useless. |
| **Metrics** (3 to 5\) | Quality \+ behavioral \+ cost metrics. Each maps to user outcome. |
| **Judge method** | Per metric: exact match, LLM-as-judge, code-based, human review. |
| **Golden dataset** | Source, size (30-50 cases), scenario mix (happy/edge/failure), how you labeled it. |
| **Pass bar** | Numeric target per metric. "What number means good enough to ship." |
| **Instrumentation** | What is traced in LangSmith (runs, sub-runs, tool calls, retries, tokens, latency). |
| **Baseline run** | Eval run on the current agent before any changes. Report numbers \+ LangSmith run link. |
| **Failure analysis** | Top 3 failure modes by frequency, with one example trace per mode and rough cost. |
| **Improvement hypotheses** (3 to 4\) | Specific changes (prompt, model, retrieval, tool, control flow) with predicted impact per metric. |
| **Post-improvement run** | Eval run after changes. Report numbers \+ delta \+ LangSmith run link. |
| **What is next** | Top remaining failure mode, what you would try if you had another week, monitoring strategy for production. |

| Tips before you fill it in Pick metrics in pairs. A quality metric (faithfulness, recall) alone lets you cheat with cost (slow, expensive). A cost metric alone lets you cheat with quality. Always measure both. Trace before you measure. Get LangSmith tracing working on a single run first. Make sure you can see every tool call, every retry, every token. Then build the dataset. Then run evals. Cluster failures before fixing. Twenty random failures are not twenty bugs. They are usually 2 to 3 root causes. Find the cluster, fix the root cause, measure the lift. |
| :---- |

# 

# **Part 2: Eval Types and Metric Library**

LangSmith supports several evaluator types. You will likely combine at least two. Pick by signal-to-noise: code-based is precise but narrow, LLM-as-judge is flexible but needs calibration, human is the gold standard but slow.

| Evaluator type | What it does | When to use | Examples |
| :---- | :---- | :---- | :---- |
| **Code-based** | A function that returns a score from comparing output to a reference. | When the right answer is deterministic and machine-checkable. | Exact match, JSON schema valid, contains keyword, regex match, numeric within tolerance. |
| **LLM-as-judge** | Another LLM scores the output against a rubric you write. | When quality is subjective but a rubric can capture it. | Faithfulness, relevance, tone match, helpfulness, hallucination check. |
| **Human review** | You or a domain expert labels each output by hand. | For the highest-stakes metrics, or to calibrate LLM-as-judge. | Manager-rated usefulness, expert-rated correctness, customer satisfaction. |
| **Trajectory eval** | Scores not just the final output but the steps taken. | For agents where the path matters (wrong tool order, unnecessary calls). | Tool selection accuracy, step count, retry behavior, hand-off timing. |

## **Metric library by use case type**

Pick 3 to 5 metrics. Always combine at least one quality metric with at least one cost/latency metric.

| Metric category | Common metrics \+ when to use |
| :---- | :---- |
| **Quality (RAG / Q\&A)** | Faithfulness (does answer match retrieved context), Answer Relevance, Context Precision/Recall, Citation Accuracy, Refusal Rate on out-of-scope questions. |
| **Quality (Agentic)** | Task Completion Rate, Tool Selection Accuracy, Trajectory Correctness, Step Count vs Optimal, Hand-off Appropriateness, Error Recovery Rate. |
| **Quality (Generative)** | Brand Voice Match, Tone Match, Structural Compliance (length, format), Factuality vs Source, No-Hallucination Rate. |
| **Behavior / Safety** | Guardrail Compliance (no PII leaks, no unsafe content), Refusal on Forbidden Inputs, Escalation Triggered Correctly, Drift over Time. |
| **Cost / Latency** | p50 / p95 latency, Cost per Run, Token Usage, Tool Call Count, Cache Hit Rate. |

# 

# **Part 3: Building Your Golden Dataset**

Your golden dataset is the heart of your evaluation. If it is not representative, your numbers lie. Spend real time on this. 30 to 50 cases is the sweet spot for Week 4\.

## **Scenario mix**

Aim for this rough distribution across your 30 to 50 cases.

| Scenario type | Share | What it includes |
| :---- | :---: | :---- |
| **Happy path** | **50%** | The common, well-formed inputs your agent should obviously handle. If these fail, you have not shipped anything. |
| **Edge cases** | **30%** | Plausible but tricky: ambiguous inputs, partial data, multiple valid answers, out-of-scope questions that should be refused gracefully. |
| **Known failures** | **15%** | Things you already know break or are hard. Cases your demo skipped. The point is to measure improvement on what hurts. |
| **Adversarial** | **5%** | Prompt injection, jailbreak attempts, irrelevant questions, malformed inputs. Tests guardrails and refusal behavior. |

## **Where to source cases**

In order of preference. Real beats synthetic, always.

| Real user data (preferred) | Production logs, ticket archives, past Slack threads, historical emails, real PRs from your repo. Anonymize first. |
| :---- | :---- |
| **Synthetic from real seeds** | Take real cases and vary them (paraphrase, swap entities, change difficulty) with an LLM. Always label by hand. |
| **LLM-generated** | Last resort. Useful for adversarial cases. Limit to under 20% of your dataset, and treat generated labels as suspect until you check them. |
| **Public benchmarks** | MS MARCO, HotpotQA, AgentBench, etc. Useful for sanity checks, but rarely match your specific task. Do not rely on them alone. |

| Golden dataset rules Every case has a known correct answer or expected behavior. If you cannot say what "right" looks like for a case, you cannot score it. Either label it or cut it. Store as a LangSmith dataset, not a CSV. Use the LangSmith Dataset UI or SDK. This is what lets you re-run evals over time and compare versions. Version your dataset. Tag the dataset version used for baseline and re-evaluation. If you change the dataset mid-week, your delta is meaningless. |
| :---- |

# 

# **Part 4: LangSmith Playbook**

LangSmith handles tracing, datasets, evaluators, and run comparisons. The minimum viable setup is below. You will use the same project across all four phases.

## **Minimum viable setup**

| 1\. Create a project | In LangSmith, create a new project named after your agent (e.g., "deal-review-eval"). All traces, datasets, and runs live under this project. |
| :---- | :---- |
| **2\. Enable tracing** | Set env vars: LANGCHAIN\_TRACING\_V2=true, LANGCHAIN\_API\_KEY=..., LANGCHAIN\_PROJECT=.... For LangChain/LangGraph apps, this is enough. For n8n, use the LangSmith HTTP node or a custom Code node hitting the API. |
| **3\. Run your agent once** | Trigger a single end-to-end run. Confirm in the LangSmith UI you see: the top-level run, every LLM call, every tool call, latency, and token cost. If anything is missing, fix tracing before moving on. |
| **4\. Upload your golden dataset** | Use the LangSmith Datasets UI or \`client.create\_dataset()\` in the SDK. Each example has inputs, expected outputs (when applicable), and metadata (scenario type, difficulty). |
| **5\. Write your evaluators** | Code-based evaluators are Python functions returning a score. LLM-as-judge evaluators use a prompt template \+ a model. Register them with the dataset. |
| **6\. Run the eval** | Use client.evaluate(agent, data, evaluators) in the SDK. Each run is recorded under your project, with per-metric scores and full traces, so you can drill into individual failures. |
| **7\. Compare runs** | Use the LangSmith Comparison view to diff baseline vs post-improvement runs. Look at per-metric delta, per-case improvement/regression, and trace-level differences. |

## **What to monitor in production**

Beyond batch eval, decide what you would alert on if this agent were live.

| Quality drift | Faithfulness or task-completion drops by more than X% over a 7-day rolling window. |
| :---- | :---- |
| **Cost spike** | p95 cost-per-run exceeds budget by more than 25% over 24 hours (often signals a retrieval or tool-loop regression). |
| **Latency regression** | p95 latency exceeds SLA on more than 5% of runs. |
| **Guardrail trips** | Any refusal, PII redaction, or escalation rate change of more than 2x baseline. |
| **Tool failure rate** | Any single tool exceeds 5% failure rate over 1 hour (often signals an external dependency outage). |

# 

# **Part 5: Improvement Playbook**

Once you have failure clusters from your baseline run, pick 3 to 4 targeted improvements. Below is a menu of common levers, in rough order of impact-per-hour. Pick what matches your dominant failure mode.

| Lever | What to try | Symptoms it fixes |
| :---- | :---- | :---- |
| **Prompt engineering** | Refine system prompt, add few-shot examples, restructure the task, add explicit instructions for refusals. | Hand-waving in instructions, inconsistent format, refusal failures, tone drift. |
| **Retrieval tuning (RAG)** | Re-chunk, switch embedding model, add re-ranking, switch to hybrid search, expand query, filter by metadata. | Faithfulness failures, irrelevant context, missing answers when info exists in corpus. |
| **Tool design** | Rewrite tool descriptions, split a multi-purpose tool into focused ones, add input validation, return richer errors. | Wrong tool selected, agent loops on the same tool, tool calls with malformed inputs. |
| **Control flow** | Switch pattern (ReAct \-\> plan-execute, single-agent \-\> supervisor), add explicit step caps, add a planning step, add a verification step. | Too many tool calls, missed steps, agent gives up, no recovery from partial failure. |
| **Model upgrade** | Swap to a larger/newer model for the critical step. Often the most expensive lever, but sometimes the only fix. | Reasoning failures on complex multi-hop or multi-step tasks that prompt engineering cannot fix. |
| **Add guardrails** | Pre-call input filters, post-call output filters, structured output schemas, explicit refusal triggers. | Hallucinations, PII leaks, unsafe content, format violations. |
| **Human-in-the-loop** | Add approval gates before write actions, add a review step on low-confidence outputs. | High-stakes failures where the agent could do real damage. Better safe than fully autonomous. |

| How to report improvements For each of your 3 to 4 improvements: name the lever, the specific change, the failure cluster it targeted, the predicted impact, and the measured delta. "Switched embedding model from MiniLM to BGE-large; targeted faithfulness failures on long-context queries; predicted \+5% faithfulness; measured \+7% faithfulness, p95 latency \+400ms." Honesty wins. If an improvement made things worse, report that. Negative deltas are useful signal. Pretending everything worked is not. |
| :---- |

# 

# **How to submit**

## **Deliverables for Week 4**

Submit the completed materials for the track you worked on. 

**Social Media Post Evaluation**

* Completed Social Media Post Evaluation spreadsheet   
* **LLM-as-a-Judge materials (optional)**: judge prompt or notebook, judge outputs, agreement comparison against human labels, disagreements, and notes on any judge model changes tried.

**Customer Support Agent Evaluation**

* Completed customer support evaluation spreadsheet with reviewed/corrected ground truth labels, model predicted labels, PASS/FAIL comparison, and participant-assigned failure categories.  
* **LLM-as-a-Judge notebook** (optional) aligned with the spreadsheet, including judge results, human-vs-judge comparison, and judge model comparison/change notes.

**Final submission**

* Upload the spreadsheet, solution doc with prompts/screenshots where applicable, notebook (where applicable), and a short Loom walkthrough explaining what changed, what improved, and what still fails.

## **Handouts for use-cases**

Given below are some handouts that we have put together for the use cases shared in this particular week's suggested use case section (part 1). You must go through this before you get started with your project, because it will direct your thinking in a particular direction. 

| \# | Use case | Data and Materials | Handout  |
| :---- | :---- | :---- | :---- |
| 1 | Customer Support Agent Evaluation | [Week 4: AI Evals (E-Commerce Customer Support Agent)](https://docs.google.com/spreadsheets/d/1DQXHydc-zx2fPh9flEwUKXyIMERs153CBvbLzUqqZWw/edit?usp=sharing) | [Customer Support Agent Evaluation Project Handout](https://docs.google.com/document/d/1zsxSbgZxsLVNVeOx3n95w555xAykzqZM9ewc9a4rTtk/edit?usp=sharing) |
| 2 | Social Media Post Evaluation | [Social Media Post Evaluation](https://docs.google.com/spreadsheets/d/1NLuItt-VODBItvpRGEK6VHIdUsnuiuKiP-oGMe-M6nA/edit?usp=sharing) [Social Media Post Generation Workflow.json](https://drive.google.com/file/d/1zLVFe5N6yIaT7OuFWsDz1QdkFAjBtRmI/view?usp=drive_link)  | [Social Media Post Evaluation Exercise](https://docs.google.com/document/d/1tGiUY_TwSEagGAc0sL96trBsf2RK04OVu9VI_rTx7pA/edit?usp=sharing) [Loom](https://www.loom.com/share/12e27b10b4604d89b2672b1759a543c4) |
| 3 | Evaluate one of your own projects using spreadsheets or LangSmith |  | [Evaluations Using LangSmith](https://docs.google.com/document/d/1UTxmO98N0Mr-87rQjdrd583Tg-xWpT1lscwrlrS0B_w/edit?usp=sharing) |

