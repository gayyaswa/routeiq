**THE GEN ACADEMY** Week 5  |  Fine-Tuning Systems

Week 5 Project

**Fine-Tune a Support Ticket Router**

Mastering Agentic AI Bootcamp  |  The Gen Academy

Github Link to the notebook: [https://github.com/The-Gen-Academy/Week-5-Projects](https://github.com/The-Gen-Academy/Week-5-Projects) 

**Project deadline:** 

* Submission link: [https://forms.gle/rrX5ZuKMzPdjzBnj7](https://forms.gle/rrX5ZuKMzPdjzBnj7)   
* 2nd July- 11pm PST (for being considered for AI Builder of the Week)  
* **Make sure that all the links have viewer-to-all access.**   
* **If any questions \- please email [tanish@thegenacademy.com](mailto:tanish@thegenacademy.com)**  
* **PS: Evaluation rubric for this week will be pass or fail based on if you were successfully able to run the notebook or not**

# **What this week is about**

This project turns a general Qwen3 model into a small, practical support-ticket router. Instead of asking a frontier model to classify every ticket forever, you fine-tune a 1.7B model on labelled examples and evaluate whether it can make the same routing decision faster and cheaper.

By the end, you will have installed LLaMA Factory, prepared a support-ticket dataset, trained a LoRA adapter through LLaMA Board, merged the adapter, smoke-tested inference, and compared the fine-tuned model against a baseline.

## **The business case**

The notebook frames fine-tuning as a systems decision, not a model leaderboard exercise. An internal IT support team handles a steady stream of tickets across email, Slack, and a help portal. Today every ticket touches a human before it reaches the right resolver queue.

| Routing label | Downstream action |
| :---- | :---- |
| Active Directory | Identity and access queue; account setup, deactivation, permissions, and directory access. |
| Computer-Services | Endpoint and hardware queue; devices, printers, workstations, and local computer issues. |
| EOL | Lifecycle queue; end-of-life, retirement, decommissioning, and replacement requests. |
| Fileservice | File storage and access queue; shared drives, folders, file permissions, and storage issues. |
| O365 | Microsoft 365 queue; Outlook, Teams, mailbox, calendar, SharePoint, and Office app issues. |
| Software | Application support queue; installs, licensing, updates, and software troubleshooting. |
| Support general | General triage queue; requests that need human review or do not fit a specific technical queue. |

**The model never writes a customer response. It reads the ticket, predicts one of these dataset labels, and routes the ticket to the right downstream queue. The rest of the support tooling takes over.**

# **How this project works**

| Phase | Notebook area | What you do |
| :---- | :---- | :---- |
| 1 | Install Dependencies | Use a free Tesla T4 runtime, clone LLaMA-Factory, and install the package dependencies. |
| 2 | Prepare Support Ticket Dataset | Upload support\_tickets.csv, create a stratified 80/20 train/validation split, convert train rows to ShareGPT JSON, and register support\_tickets in dataset\_info.json. |
| 3 | Fine-tune via LLaMA Board | Open the public LLaMA Board URL, choose Qwen/Qwen3-1.7B-Base, select support\_tickets, set finetuning to LoRA, and train. |
| 4 | Review Training | Check the loss curve. It should drop and then level off; a flat or chaotic curve means something is wrong. |
| 5 | Merge \+ Smoke Test | Set ADAPTER\_DIR, merge the LoRA adapter into the base model, define classify(), and run fast sanity checks. |
| 6 | Evaluate \+ Compare | Run validation inference, inspect precision/recall/F1 and confusion matrix, then compare baseline vs fine-tuned accuracy. |

# **Participant inputs**

| Input | Where it is used | Why it matters |
| :---- | :---- | :---- |
| support\_tickets.csv | Prepare Support Ticket Dataset | Source labelled examples for training and validation. |
| Qwen/Qwen3-1.7B-Base | LLaMA Board train tab | Base model that will receive the LoRA adapter. |
| support\_tickets | LLaMA Board dataset field | Dataset name registered in LLaMA Factory. |
| Output Dir / ADAPTER\_DIR | Review \+ Merge cells | Path to the trained LoRA adapter produced by LLaMA Board. |

# **Training choices to understand**

Use the defaults for a first run, then tune only when the first result underperforms. The notebook calls out learning rate, epochs, batch size, and LoRA rank as the knobs most worth touching.

| Choice | Default interpretation | When to adjust |
| :---- | :---- | :---- |
| LoRA finetuning | Train a small adapter while the base model stays frozen. | Use this for fast Colab training and low VRAM usage. |
| Learning rate | How aggressively the adapter updates. | Lower it if loss oscillates; raise carefully if loss barely moves. |
| Epochs | How many passes over the training split. | Increase if loss is still improving; stop if validation performance regresses. |
| Batch size | How many examples contribute to each update. | Adjust for GPU memory and training stability. |
| LoRA rank | Adapter capacity. | Increase if the task needs more capacity; keep modest for a small router. |

## **Why merge the LoRA adapter?**

During training, the base model weights stay frozen and the adapter stores the learned routing deltas. For inference, merging folds those deltas back into the base weights so you have a single standalone model with no adapter overhead.

# **Evaluation: what to look for**

The validation split was held out during training, so it is the honest read on routing performance. Do not stop at overall accuracy; support routing has asymmetric costs.

| Evaluation view | How to read it |
| :---- | :---- |
| Classification report | Precision, recall, F1, and support by class. High-urgency categories should have strong recall, even if overall accuracy is lower. |
| Confusion matrix | Rows are true classes, columns are predictions. Off-diagonal cells show specific routing confusions to investigate. |
| Smoke test | Five obvious tickets should route correctly before you run the full validation loop. If they fail, check checkpoint, template, or training. |
| Baseline comparison | The same base model is evaluated on the same validation tickets with no task-specific training. The delta is the measurable value of the fine-tuning run. |

## **Baseline vs fine-tuned comparison**

The baseline uses a constrained letter-choice prompt so the base model cannot fail just because it prints a label variant like AD instead of Active Directory. The fine-tuned model uses the merged router through classify().

* A large positive delta means the model learned routing signal from your labelled examples.  
* A class with zero baseline and strong tuned performance is a clear fine-tuning win.  
* A class regression usually points to sparse data, ambiguous labels, or a hyperparameter issue.

# **How to submit / demo your result**

* Submit a Google Doc which has a screenshot of your successful run in the notebook.  
* Submit it here: [https://forms.gle/rrX5ZuKMzPdjzBnj7](https://forms.gle/rrX5ZuKMzPdjzBnj7)  
* **If you are trying to build something custom and explore your own ideas, instead of the Google Doc, you can submit a GitHub link which has all the assets.**

The Gen Academy  |  Mastering Agentic AI Bootcamp  |  Week 5