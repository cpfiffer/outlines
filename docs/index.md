---
title: Welcome to Outlines!
---

# Outlines

Outlines is a Python library from [.TXT](https://dottxt.co) that guarantees structured output from 
large language models. It ensures LLMs speak the language of your application by making them follow specific formats such as JSON, regular expressions, or context-free grammars.

[Get started](/docs/getting_started){ .md-button .md-button--primary }
[API Reference](/api/reference){ .md-button }
[Examples](/examples){ .md-button }
[GitHub](https://github.com/yourusername/outlines){ .md-button }

## Features

<div class="grid cards" markdown>

- :material-shield-check: __Reliable__ - Guaranteed schema compliance -- always valid JSON.
- :material-puzzle: __Feature-rich__ - Supports a large proportion of the JSON Schema spec, along with regex and context-free grammars.
- :material-lightning-bolt: __Fast__ - Outlines has negligible runtime overhead, and fast compilation times.
- :material-cog: __Universal__ - Outlines is a powered by Rust, and can be easily bound to other languages.
- :material-lightbulb: __Simple__ - Outlines is a low-abstraction library. Write code the way you normally do with LLMs. No agent frameworks needed.
- :material-magnify: __Powerful__ - Manage prompt complexity with prompt templating.

</div>

## Installation

We recommend using `uv` to install Outlines. You can find installation instructions [here](https://github.com/astral-sh/uv).

```bash
uv pip install 'outlines[transformers]'
```

or the classic `pip`:

```bash
pip install 'outlines[transformers]'
```

## Quick start

> [!NOTE]
> - [ ] This section should include tabs for each of the different inference backends.
> - [ ] Add comments to the code example to explain what it does.

### JSON

```python
import json
from outlines import models
from pydantic import BaseModel, Field
from transformers import AutoModelForCausalLM, AutoTokenizer

class Person(BaseModel):
    name: str
    age: int
    email: str = Field(pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


model_id = "HuggingFaceTB/SmolLM2-135M-Instruct"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(model_id)

model = models.from_transformers(
    model,
    tokenizer
)

person_text = """
John Doe
30
john.doe@example.com
"""

prompt = tokenizer.apply_chat_template(
    [
        {"role": "system", "content": "Extract the person information from this text."},
        {"role": "user", "content": person_text}
    ],
    tokenize=False,
    add_generation_prompt=True
)

result = model(
    prompt, 
    Person,
    max_new_tokens=100
)
print(result)
```

Result:
```json
{
    "name": "John Doe",
    "age": 30,
    "email": "john.doe@example.com"
}
```

### Regex

> [!NOTE]
> Insert regex example here

### Multiple choice

> [!NOTE]
> Insert multiple choice example here

## Supported models

> [!NOTE]
> Provide full model list with links to docs about each model

- vLLM
- Transformers
- OpenAI


## About .txt

Outlines is built with ❤️ by [.txt](https://dottxt.co). 

.txt solves the critical problem of reliable structured output generation for large language models. Our commercially-licensed libraries ensure 100% compliance with JSON Schema, regular expressions and context-free grammars while adding only microseconds of latency. Unlike open-source alternatives, we offer superior reliability, performance, and enterprise support.

Schedule a [demo call](https://cal.com/team/dottxt/sales) to learn more about how .txt can help you integrate LLMs into production environments without additional engineering resources.
