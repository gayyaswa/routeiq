---
library_name: peft
license: other
base_model: Qwen/Qwen3-1.7B-Base
tags:
- llama-factory
- lora
- generated_from_trainer
model-index:
- name: intent_adapter_v2
  results: []
---

<!-- This model card has been generated automatically according to the information the Trainer had access to. You
should probably proofread and complete it, then remove this comment. -->

# intent_adapter_v2

This model is a fine-tuned version of [Qwen/Qwen3-1.7B-Base](https://huggingface.co/Qwen/Qwen3-1.7B-Base) on the day_trip_intent dataset.

## Model description

More information needed

## Intended uses & limitations

More information needed

## Training and evaluation data

More information needed

## Training procedure

### Training hyperparameters

The following hyperparameters were used during training:
- learning_rate: 0.0002
- train_batch_size: 2
- eval_batch_size: 8
- seed: 42
- gradient_accumulation_steps: 8
- total_train_batch_size: 16
- optimizer: Use adamw_torch with betas=(0.9,0.999) and epsilon=1e-08 and optimizer_args=No additional optimizer arguments
- lr_scheduler_type: cosine
- num_epochs: 3.0

### Training results



### Framework versions

- PEFT 0.15.2
- Transformers 4.51.3
- Pytorch 2.8.0
- Datasets 3.6.0
- Tokenizers 0.21.1