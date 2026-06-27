

Project Handout: Social Media Post Evaluation  
Exercise

**Introduction**

Reliable AI systems require more than intuition. Just because an LLM output *looks* good does not mean it is ready for a production workflow. The goal of this project is to move beyond subjective review and build a systematic **Evaluation Loop.**

In this exercise, you will generate social media posts using an n8n workflow, score them using a rubric, identify failure patterns, apply fixes to the system prompt, run regression tests, and build an LLM-as-a-Judge to automate part of the grading process.

**Prerequisites**

* Access to the provided [**n8n workflow** JSON](https://drive.google.com/file/d/1zLVFe5N6yIaT7OuFWsDz1QdkFAjBtRmI/view?usp=drive_link).  
* The [Social Media Post Evaluation](https://docs.google.com/spreadsheets/u/2/d/1NLuItt-VODBItvpRGEK6VHIdUsnuiuKiP-oGMe-M6nA/edit) spreadsheet.  
* The [n8n setup guide](https://www.loom.com/share/12e27b10b4604d89b2672b1759a543c4) for this project.  
* A cup of coffee (optional, but recommended).

**Part 1: Data Generation**

**Step 1: Run the Workflow**

Run the n8n workflow for your test topic. The Model\_Output column of your spreadsheet should be populated with the generated post content.

**Step 2: Score Each Post**

Evaluate every post on a scale of 1-5, where 1 \= Poor and 5 \= Excellent, across these five dimensions:

| Criterion | Definition |
| :---- | :---- |
| **Factual Correctness** | Does the post contain hallucinations, wrong dates, or technical errors? |
| **Clarity** | Is the writing concise, coherent, and easy to read? |
| **Value / Insight** | Does it offer a unique perspective, or is it generic "fluff"? |
| **Engagement** | Is there a strong hook? Is there a clear call to action? |
| **Tone Fit** | Does it match the intended persona: professional, clear, and accessible? |

**Step 3: Apply the Pass/Fail Threshold**

For routing or classification tasks, PASS vs. FAIL is often straightforward: the model either matched the expected intent, or it did not. For social media generation, the decision is more subjective and depends on which dimensions matter most for the product use case.

Use the following strict logic to determine the final status of each post:

| PASS / FAIL ALGORITHM |
| :---- |
| **FAIL if:** Factual Correctness score is \< **4**. This is a zero-tolerance rule for hallucinations. **FAIL if:** Total Score, the sum of all five metrics, is \< **20**. **PASS if:** neither of the above conditions are met. |

**Part 2: Error Analysis**

After scoring, review every post marked as **FAIL** and assign a **Failure Category**. Do not simply fix the text. Identify the *systemic error* that caused the bad output.

| Failure Category | Errors & Root Cause |
| :---- | :---- |
| **1\. Incorrect or Hallucinated Content** | **Error:** wrong dates, made-up features, false quotes.**Cause:** the model lacks required context or grounding. |
| **2\. Low Informational Value** | **Error:** generic advice, overuse of buzzwords, lack of depth.**Cause:** the model is auto-completing familiar patterns without reasoning through the topic. |
| **3\. Instruction Non-Compliance** | **Error:** the model misunderstood the task, ignored the requested format, or missed a key constraint.**Cause:** the prompt likely used vague wording or failed to define the required structure. |
| **4\. Poor Framing** | **Error:** boring hook, robotic tone, weak narrative, sounds AI-generated.**Cause:** the model lacks a clear stylistic target or examples to imitate. |

If you see a recurring error pattern that does not fit these categories, create a new failure category and specify its defining errors and likely root cause.

**Part 3: The Fix**

Determine which failure category is most relevant for this use case. For example, if most failures are caused by low informational value, your fix should target depth and specificity rather than tone or formatting.

Apply the corresponding engineering fix to the system prompt in n8n.

| Error Correction |
| :---- |
| **If Hallucination:** \-\> **Context Injection.***Action:* paste the specific source text, product facts, campaign brief, or topic background into the system prompt context. **If Low Info Value:** \-\> **Reasoning Scaffold.***Action:* add an instruction such as: "Before writing the post, identify 3 specific, non-obvious insights about this topic." **If Non-Compliance:** \-\> **Positive Framing.***Action:* replace vague negative constraints with direct positive instructions. For example, change "Do not use emojis" to "Write in strict plain text only." **If Poor Framing:** \-\> **Few-Shot Prompting.***Action:* provide 3 examples of strong posts directly in the prompt for the model to mimic. |

**Part 4: Regression Testing**

After updating your n8n workflow:

1. **Re-run** the specific inputs that failed previously.  
2. **Check for regressions:** re-run at least one input that previously *passed*.  
3. Compare the new output to the old output.  
4. Did the failed post flip to **PASS**? Did the passing post stay **PASS**?

**Part 5: LLM-as-a-Judge (Optional)**

Manual grading does not scale. The goal of this section is to build an LLM-based judge that approximates human evaluation and can be plugged into your workflow for continuous, scalable grading.

**Step 1: Create the Judge Prompt**

Design a **system prompt** for a separate LLM whose sole task is to evaluate social media posts.

* Score each post on the five rubric dimensions.  
* Output PASS/FAIL using the logic from Part 1\.  
* If FAIL, assign a Failure Category from Part 2\.

Optional reference implementation: llm\_as\_judge.ipynb

**Step 2: Measure Judge Accuracy**

Compare judge outputs against your human-labeled spreadsheet:

* Compute PASS/FAIL agreement.  
* Inspect disagreements.  
* Identify whether the judge is too lenient, too strict, or misunderstanding a rubric dimension.

| Aligning an LLM-as-a-Judge |
| :---- |
| Alignment means the judge agrees with your human labels. If your spreadsheet says **FAIL** and the judge says **PASS**, the judge is misaligned and must be calibrated. |

**Step 3: Calibrate the Judge**

Iteratively improve the LLM-as-a-Judge by tweaking the prompt, adding few-shot examples, clarifying rubric definitions, or changing the model. Stop when the judge reliably matches human decisions on held-out examples.

**Submission:** Upload your completed spreadsheet, a screenshot of your updated n8n prompt, and your LLM-as-a-Judge implementation to the project submission channel.