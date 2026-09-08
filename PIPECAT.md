# Pipecat Reference — Build Guide for This Voice Agent

Research notes on the [Pipecat](https://github.com/pipecat-ai/pipecat) framework, compiled as a
reference for building our voice agent. Project-specific requirements will be layered on top of
this once provided.

> Sources: [docs.pipecat.ai](https://docs.pipecat.ai), [github.com/pipecat-ai/pipecat](https://github.com/pipecat-ai/pipecat),
> [github.com/pipecat-ai/pipecat-flows](https://github.com/pipecat-ai/pipecat-flows) (now merged into core),
> verbatim example source from `pipecat-ai/pipecat` and `pipecat-ai/pipecat-quickstart` repos.
> Verified against the current (2026) API surface — **note that a lot of blog posts/tutorials predate
> a naming change** (see [Two runner APIs](#two-runner-apis-pipelinetask-vs-pipelineworker) below);
> don't trust older tutorials' class names without checking here first.

## 1. What Pipecat is

Open-source Python framework (BSD-2-Clause, maintained by Daily) for building real-time voice and
multimodal conversational agents. It handles the hard real-time plumbing — audio I/O, interruption
handling, turn-taking, streaming — so application code is just wiring together services.

- Docs: https://docs.pipecat.ai
- Examples: https://github.com/pipecat-ai/pipecat/tree/main/examples and the separate
  https://github.com/pipecat-ai/pipecat-examples repo (client/server demos, telephony, avatars)
- Discord: https://discord.gg/pipecat

## 2. Core architecture

Three concepts:

1. **Frames** — data units flowing through the system: audio, video, text, transcription, or
   control signals. Every frame gets an auto-assigned id for debugging/tracing.
2. **FrameProcessors** — the building blocks. Each receives frames, does its job, and pushes
   frames downstream (and sometimes upstream). Processors don't "consume" frames — they pass
   everything along, so multiple processors can react to the same stream.
3. **Pipeline** — an ordered list of FrameProcessors wired together. A `Pipeline` is itself a
   processor, so pipelines can nest (see `ParallelPipeline` below).

### Frame categories

| Category | Priority | Examples | Notes |
|---|---|---|---|
| `SystemFrame` | highest, own queue | `InputAudioRawFrame`, `UserStartedSpeakingFrame`, `InterruptionFrame`, `ErrorFrame` | Never discarded on interruption; jumps the queue |
| `DataFrame` | ordered | `OutputAudioRawFrame`, `TextFrame`, `TranscriptionFrame`, `LLMTextFrame`, `TTSTextFrame` | Normal payload frames |
| `ControlFrame` | ordered | `StartFrame`, `EndFrame`, `TTSStartedFrame`, `LLMFullResponseStartFrame` | Lifecycle / boundary markers |

Pipeline lifecycle: a `StartFrame` propagates through every processor first (each opens
connections / loads models), then data flows, then an `EndFrame` (or `CancelFrame` for abrupt
stop) tears it down in order.

### ParallelPipeline

Branches that each receive a full copy of the upstream frame stream independently — typically
paired with filters, used for things like running two LLMs / two output modalities off one input
stream (see multi-agent section).

## 3. Two runner APIs: `PipelineTask` vs `PipelineWorker`

Pipecat currently exposes **two ways to run a pipeline** — don't mix them up:

- **Simple / single-agent** (`pipecat.pipeline.task.PipelineTask` +
  `pipecat.pipeline.runner.PipelineRunner`): the classic pattern, used by the plain quickstart.
  Good default for a single bot with no multi-agent handoff.
- **Worker-based** (`pipecat.pipeline.worker.PipelineWorker` +
  `pipecat.workers.runner.WorkerRunner`): newer API that adds `idle_timeout_secs`,
  `ProcessorUnusablePolicy`, and support for running multiple workers on a shared **worker bus**
  (needed for multi-agent handoff/coordination, see §6). `FlowManager` in the flows examples is
  built on this.

Rule of thumb: start with `PipelineTask`/`PipelineRunner` for a single bot; move to
`PipelineWorker`/`WorkerRunner` if you need Pipecat Flows' node-graph conversation control, or
multiple cooperating agents.

## 4. Minimal single-agent bot (verbatim, `PipelineTask` style)

From `pipecat-ai/pipecat-quickstart/bot.py`:

```python
import os
from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams

load_dotenv(override=True)

async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))
    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        settings=CartesiaTTSService.Settings(voice="71a7ad14-091c-4e8e-a314-022ece01c121"),
    )
    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        settings=OpenAILLMService.Settings(
            system_instruction="You are a friendly AI assistant. Respond naturally and keep your answers conversational.",
        ),
    )

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context, user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer())
    )

    pipeline = Pipeline([
        transport.input(),
        stt,
        user_aggregator,
        llm,
        tts,
        transport.output(),
        assistant_aggregator,
    ])

    task = PipelineTask(pipeline, params=PipelineParams(enable_metrics=True, enable_usage_metrics=True))

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        context.add_message({"role": "developer", "content": "Say hello and briefly introduce yourself."})
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
    await runner.run(task)

async def bot(runner_args: RunnerArguments):
    transport_params = {
        "daily": lambda: DailyParams(audio_in_enabled=True, audio_out_enabled=True),
        "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    }
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)

if __name__ == "__main__":
    from pipecat.runner.run import main
    main()
```

Key pattern: `bot(runner_args: RunnerArguments)` is the entry point the CLI/cloud runner calls;
`create_transport` picks the transport implementation (Daily, WebRTC, Twilio, etc.) based on how
it's invoked, so the same `bot.py` runs locally and in production without code changes.

Scaffolding: `uv tool install "pipecat-ai[cli]"` then `pipecat init quickstart`.
Run: `uv sync && uv run bot.py`. Deploy: `pipecat cloud deploy`.

## 5. Structured conversations: Pipecat Flows

`pipecat_flows` (standalone package) was **merged into core pipecat as of 1.5.0** — import from
`pipecat.flows`, not the old `pipecat_flows` package:

```python
# old (deprecated standalone package)
from pipecat_flows import FlowManager, NodeConfig
# current
from pipecat.flows import FlowManager, NodeConfig
```

Use Flows when the conversation has real structure — a sequence of steps/states with
different valid actions at each (reservations, intake forms, IVR-style menus, support triage) —
rather than one open-ended system prompt.

Concepts:
- **NodeConfig** — one conversation state: `name`, `role_message` (persona, usually only on the
  first node), `task_messages` (what the bot should do right now), `functions` (tools callable in
  this node), `pre_actions`/`post_actions` (side effects, e.g. `{"type": "end_conversation"}`),
  `context_strategy`, `respond_immediately`.
- **Functions drive transitions.** A node's function handler returns
  `tuple[result, next_node]` — `result` goes back to the LLM as the tool result, `next_node` is
  the `NodeConfig` to transition to (or `None` to stay). This is how the graph is actually defined
  — edges are just "what NodeConfig does this function return."
- **Dynamic flows are the current recommendation.** Static, fully pre-declared flow graphs are
  deprecated (removal planned for v1.0.0) — build node configs in Python functions at runtime
  instead (as in the example below), which is more flexible for data-dependent branching.
- **Schema from function signature + docstring.** Prefer plain async functions —
  `async def fn(flow_manager: FlowManager, arg: type) -> tuple[Result, NodeConfig]` — Flows
  derives the LLM tool schema from the type hints and a Google-style docstring `Args:` section.
  Use `FlowsFunctionSchema` directly only when you need strict enums/numeric bounds the
  auto-derivation can't express yet (it doesn't map `Literal` → JSON-schema `enum` currently —
  describe constraints in the docstring prose instead as a workaround).
- **State**: `flow_manager.state` is a plain dict shared across every node for the life of the
  conversation — store collected slot values, DB handles, etc. there.
- **Global functions**: pass `global_functions=[...]` to `FlowManager` for tools that should be
  callable from every node (e.g. "transfer to a human"), instead of repeating them per node.

### Verbatim example — restaurant reservation (dynamic flow)

From `pipecat-ai/pipecat/examples/flows/restaurant_reservation.py` (trimmed to the shape that
matters; full functions/nodes elided for brevity — see repo for the complete file):

```python
from pipecat.flows import FlowManager, NodeConfig
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
from pipecat.workers.runner import WorkerRunner

async def collect_party_size(flow_manager: FlowManager, size: int) -> tuple[dict, NodeConfig]:
    """Record the number of people in the party.

    Args:
        size (int): Number of people in the party. Must be between 1 and 12.
    """
    result = {"size": size, "status": "success"}
    next_node = create_time_selection_node()
    return result, next_node

def create_initial_node(wait_for_user: bool) -> NodeConfig:
    return NodeConfig(
        name="initial",
        role_message="You are a restaurant reservation assistant for La Maison...",
        task_messages=[{"role": "developer", "content": "Warmly greet the customer and ask how many people are in their party."}],
        functions=[collect_party_size],
        respond_immediately=not wait_for_user,
    )

def create_end_node() -> NodeConfig:
    return NodeConfig(
        name="end",
        task_messages=[{"role": "developer", "content": "Thank them and end the conversation."}],
        functions=[],
        post_actions=[{"type": "end_conversation"}],
    )

async def run_bot(transport, runner_args, wait_for_user: bool = False):
    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY", ""))
    tts = CartesiaTTSService(api_key=os.getenv("CARTESIA_API_KEY", ""), ...)
    llm = create_llm()  # provider-agnostic helper in the example's utils.py

    context = LLMContext()
    context_aggregator = LLMContextAggregatorPair(context, user_params=LLMUserAggregatorParams(...))

    pipeline = Pipeline([
        transport.input(), stt, context_aggregator.user(), llm, tts,
        transport.output(), context_aggregator.assistant(),
    ])

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        processor_unusable_policy=ProcessorUnusablePolicy.END,
    )
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    flow_manager = FlowManager(
        worker=worker, llm=llm, context_aggregator=context_aggregator, transport=transport,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        await flow_manager.initialize(create_initial_node(wait_for_user))

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        await runner.cancel()

    await runner.run()
```

Multi-LLM-provider support in this example is via a `create_llm()` helper switched by an
`LLM_PROVIDER` env var (`openai_responses` default, or `openai`/`anthropic`/`google`/`aws`) — a
useful pattern if we want to A/B providers without branching bot code.

Flows quickstart (two-node "hello world," minimal case): scaffold via the Flows quickstart guide
at https://docs.pipecat.ai/pipecat/flows/quickstart — same shape as above but only a greeting node
and an end node.

## 6. Multi-agent patterns (if the project needs more than one agent)

Built on the worker/worker-bus runtime (§3). Relevant example paths in
`pipecat-ai/pipecat/examples/multi-worker/`:

- **Local handoff** (`local-handoff/`) — two agents (e.g. greeter → support) trading control
  in-process, optionally with distinct TTS voices per agent.
- **Parallel debate** (`parallel-debate/`) — multiple agents processing the same input
  concurrently (via `ParallelPipeline`-style branching) — useful for panel/roleplay-style bots.
- **Distributed handoff** (`distributed-handoff/redis-handoff`, `.../pgmq-handoff`) — agents
  running in separate processes/machines, coordinating over Redis or Postgres/Supabase (PGMQ)
  instead of an in-process bus.
- **Remote proxy assistant** — point-to-point WebSocket between agents instead of a shared bus.

Only reach for this if the project genuinely needs agent-to-agent handoff (e.g. "route to a
specialist bot" or "escalate to a human-in-the-loop agent"); a single Flows-based agent covers
most structured-conversation needs.

## 7. Transports

Transport = how audio/video gets in and out. Pick based on where users connect from:

| Transport | Use case |
|---|---|
| `DailyParams` (Daily WebRTC) | Web/mobile clients, or PSTN/SIP via Daily's dial-in/out |
| `TransportParams` (Small WebRTC) | Peer-to-peer WebRTC, no third-party service needed |
| `FastAPIWebsocketParams` | Serve over WebSocket in a FastAPI app; also what Twilio/Telnyx/Plivo/Exotel Media Streams use |
| WhatsApp transport | Inbound WhatsApp voice calls via Business Calling API |

`create_transport(runner_args, transport_params_dict)` picks the right one at runtime based on
how the process was launched — write transport-agnostic bot code and pass a dict of lambdas
keyed by transport name (`"daily"`, `"webrtc"`, `"twilio"`, etc.), as shown in both examples above.

## 8. Telephony

Three integration strategies, pick by how much call control you need:

- **WebSocket media streams** (Twilio, Telnyx, Plivo, Exotel) — simplest, good for basic
  inbound/outbound; no built-in transfer/forwarding.
- **Daily WebRTC + native PSTN/SIP** — best audio quality, supports call transfer (incl. warm
  transfer to a human — see `examples/phone-chatbot/daily-pstn-warm-transfer`).
- **Daily + SIP trunking to an existing provider** — full SIP protocol control (transfers,
  forwarding, multi-party) while keeping WebRTC transport internally.

## 9. Context management

- `LLMContext` holds the conversation message history.
- `LLMContextAggregatorPair(context, user_params=LLMUserAggregatorParams(...))` returns
  `(user_aggregator, assistant_aggregator)` — wire `user_aggregator` right after STT (or right
  before the LLM) and `assistant_aggregator` right after TTS/transport-output, so both sides of
  the conversation get appended to `context` automatically.
- `LLMUserAggregatorParams(vad_analyzer=..., filter_incomplete_user_turns=True)` — VAD-aware
  turn detection and filtering of cut-off user utterances before they hit the LLM.
- For long conversations, `LLMContextSummarizer` can compress older history; Flows node
  transitions support append/reset/summarize context strategies per-node.

## 10. Function/tool calling (non-Flows)

Even without Flows, LLM services support standard tool calling — register `FunctionSchema`s /
a `ToolsSchema` on the LLM context and provide async handlers. Reach for full Flows only when you
need node-scoped tool availability and state-machine-style transitions; for a single always-on
tool (e.g. "look up order status"), plain function calling is simpler.

## 11. Deployment options

- **Pipecat Cloud** (managed, Daily-hosted) — `pipecat cloud auth login`,
  `pipecat cloud secrets set <name> --file .env`, `pipecat cloud deploy`. Least ops work.
- **Self-hosted patterns**, pick by traffic shape:
  - *VM per session* — dispatcher spins up a fresh VM per call; simplest isolation model.
  - *Warm pool with subprocess workers* — pre-allocated long-lived host, workers replenished on
    use; lower latency/cost at moderate scale.
  - *Managed agent runtime* — hand lifecycle/scaling to a runtime, don't build your own dispatcher.
- **Turnkey hosting guides exist for**: Fly.io (VM-per-session pattern), Modal (containerized
  FastAPI, optional GPU), Cerebrium (serverless CPU/GPU).

## 12. Testing

`pipecat.evals` — scripted-conversation + semantic-assertion behavioral testing against a running
agent (`pipecat eval`). Worth setting up once the flow/node graph stabilizes, before hand-testing
every edge case manually.

## 13. Open questions for the actual project (fill in once scoped)

- [ ] Single bot or does it need Flows-style structured steps?
- [ ] Transport: web client (Daily/WebRTC) vs. telephony (which provider) vs. WhatsApp?
- [ ] STT/LLM/TTS provider choices (affects env vars / API keys needed)
- [ ] Self-host vs. Pipecat Cloud
- [ ] Multi-agent handoff needed, or single agent sufficient?
- [ ] Tool/function calling requirements (external APIs the agent needs to call)
