# Model Interface

The model interface is the first concrete layer to build.

It answers:

```text
How does Algent choose and contact an LLM?
```

## Why This Comes First

Every agent eventually needs a model call. Before defining agent runtimes,
tools, memory, artifacts, or ledgers, Algent needs a clean way to describe what
model it wants.

This is the first small proof of the larger architecture:

```text
Algent describes the need.
The selected target handles the implementation.
```

## Mental Model

The first chain is:

```text
ModelSpec -> model resolver -> concrete model object
```

Then a later step can use that object to make a simple call.

## ModelSpec

`ModelSpec` is Algent's neutral model description.

It should describe:

- provider: who hosts the model
- model name: provider-specific model id
- call settings: temperature, max tokens, timeout, max retries
- extra: an escape hatch for provider-specific options

Note: `target` is deliberately NOT a field on `ModelSpec`. Which implementation
path builds the model is a runtime concern (rail is a per-agent property), so it
is passed to the resolver instead — `resolver.resolve(spec, target="langchain")`
— with `target` defaulting to `langchain` for now. This keeps `ModelSpec` purely
about the model.

Example shape:

```text
provider = openai
model = some-model-id
temperature = 0.2
```

## Provider

A provider is the company or platform hosting the model.

Examples:

- `openai`
- `anthropic`
- `google`

Provider SDK packages are raw API clients, such as `openai` or `anthropic`.

## Target

A target is the implementation path used to instantiate the model.

The first target is:

```text
langchain
```

A possible later target is:

```text
native
```

The same provider can be reached through different targets.

```text
provider=openai, target=langchain
provider=openai, target=native
```

The first means "use OpenAI through LangChain's wrapper." The second would mean
"use OpenAI through Algent's own direct SDK harness."

## LangChain Target

The LangChain target turns `ModelSpec` into a LangChain-compatible chat model.

It can use packages such as:

- `langchain-openai`
- `langchain-anthropic`
- `langchain-google-genai`

These are not Algent's core model abstraction. They are implementation helpers
for the LangChain target.

## What The Model Interface Owns

The model interface owns:

- neutral model naming
- provider selection
- target selection
- model resolver behavior
- basic model construction options

## What The Model Interface Must Not Own

The model interface should not own:

- agent workflow execution
- LangGraph graph construction
- tool calling
- artifact writing
- run ledger storage
- GraphOS projection

Those are later layers.

## First Implementation Goal

The first implementation should prove:

```text
Given a ModelSpec, Algent can resolve a LangChain chat model object.
```

It does not need to run a full agent yet.

## Implemented Code Area (Slice 0)

Built and proven by `tests/test_model_resolution.py`:

```text
agent_system/
└── foundation/
    └── models/
        ├── specs.py         # ModelSpec — neutral request
        ├── handles.py       # ResolvedModel — concrete object + metadata
        ├── resolver.py      # ModelResolver — routing (no LangChain imports)
        └── targets/
            ├── base.py      # ModelTarget interface
            └── langchain.py # the only module importing LangChain wrappers
```

`ResolvedModel` (in `handles.py`) wraps the concrete client alongside
`provider/target/model` metadata rather than returning a raw provider object —
different targets legitimately return different object types, and we don't want
to pretend they're uniform. More structure is added only when the next subsystem
earns it.
