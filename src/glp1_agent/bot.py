import os
from datetime import UTC, datetime
from uuid import UUID

import truststore
from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.flows import FlowManager
from pipecat.observers.loggers.metrics_log_observer import MetricsLogObserver
from pipecat.observers.user_bot_latency_observer import LatencyBreakdown, UserBotLatencyObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.workers.runner import WorkerRunner

from glp1_agent.config import Settings
from glp1_agent.db.connection import create_pool
from glp1_agent.flows.nodes import NODE_BUILDERS
from glp1_agent.flows.selection import select_conversation_mode
from glp1_agent.services import Services
from glp1_agent.tools.functions import (
    STATE_ACTIVE_MEDICATION_ID,
    STATE_CHECKIN_ID,
    STATE_PATIENT_ID,
    STATE_RESOLVED_TRACKING_KEYS,
    STATE_SERVICES,
    STATE_TRACKING_ITEMS,
    STATE_TRACKING_LOOP_COUNT,
)

truststore.inject_into_ssl()
load_dotenv()

logger.add("logs/bot.log", rotation="10 MB", retention="7 days", enqueue=True)


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    settings = Settings()

    # NOTE: real call dispatch should pass patient_id via call/room metadata. Reading it from an
    # env var here is a V1 placeholder — out of scope for this pass (see plan doc).
    patient_id = UUID(os.environ["GLP1_PATIENT_ID"])

    pool = await create_pool(settings.database_url)
    services = Services.build(pool)

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY", ""))
    tts = ElevenLabsTTSService(
        api_key=os.getenv("ELEVENLABS_API_KEY", ""),
        settings=ElevenLabsTTSService.Settings(voice="21m00Tcm4TlvDq8ikWAM"),
    )
    llm = OpenAILLMService(
        api_key=settings.openai_api_key,
        settings=OpenAILLMService.Settings(model="gpt-4.1"),
    )

    context = LLMContext()
    context_aggregator = LLMContextAggregatorPair(
        context, user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer())
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    # enable_metrics=True (below) makes every service report TTFB; the TTS/LLM base
    # classes also derive TTFA/TTFAT from it automatically. These observers just log
    # what's already being computed — see docs/plan doc for the metrics wiring.
    user_bot_latency_observer = UserBotLatencyObserver()

    @user_bot_latency_observer.event_handler("on_latency_measured")
    async def on_latency_measured(observer, latency_secs: float):
        logger.info(f"patient {patient_id}: user-to-bot latency={latency_secs:.3f}s")

    @user_bot_latency_observer.event_handler("on_first_bot_speech_latency")
    async def on_first_bot_speech_latency(observer, latency_secs: float):
        logger.info(f"patient {patient_id}: first bot speech latency={latency_secs:.3f}s")

    @user_bot_latency_observer.event_handler("on_latency_breakdown")
    async def on_latency_breakdown(observer, breakdown: LatencyBreakdown):
        events = "; ".join(breakdown.chronological_events())
        logger.debug(f"patient {patient_id}: latency breakdown: {events}")

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        processor_unusable_policy=ProcessorUnusablePolicy.END,
        observers=[user_bot_latency_observer, MetricsLogObserver()],
    )
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    if worker.turn_tracking_observer is not None:

        @worker.turn_tracking_observer.event_handler("on_turn_started")
        async def on_turn_started(observer, turn_number: int):
            logger.debug(f"patient {patient_id}: turn {turn_number} started")

        @worker.turn_tracking_observer.event_handler("on_turn_ended")
        async def on_turn_ended(
            observer, turn_number: int, duration_secs: float, was_interrupted: bool
        ):
            status = "interrupted" if was_interrupted else "completed"
            logger.info(
                f"patient {patient_id}: turn {turn_number} {status} "
                f"latency={duration_secs:.3f}s"
            )

    flow_manager = FlowManager(
        worker=worker,
        llm=llm,
        context_aggregator=context_aggregator,
        transport=transport,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        checkin = await services.checkins.create(patient_id, datetime.now(UTC))
        patient_context = await services.patient_context.get_patient_context(patient_id)

        flow_manager.state[STATE_SERVICES] = services
        flow_manager.state[STATE_PATIENT_ID] = str(patient_id)
        flow_manager.state[STATE_CHECKIN_ID] = str(checkin.id)
        if patient_context.active_medication is not None:
            flow_manager.state[STATE_ACTIVE_MEDICATION_ID] = str(
                patient_context.active_medication.patient_medication_id
            )
        flow_manager.state[STATE_TRACKING_ITEMS] = patient_context.tracking_items
        flow_manager.state[STATE_RESOLVED_TRACKING_KEYS] = set()
        flow_manager.state[STATE_TRACKING_LOOP_COUNT] = 0

        mode = select_conversation_mode(patient_context)
        logger.info(f"patient {patient_id}: journey={patient_context.journey.state} mode={mode}")
        initial_node = NODE_BUILDERS[mode](patient_context)
        await flow_manager.initialize(initial_node)

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        await runner.cancel()
        await pool.close()

    await runner.run()


async def bot(runner_args: RunnerArguments) -> None:
    # WebRTC only for now — Daily/telephony support (CLAUDE.md lists "Daily/WebRTC") can be
    # added back by registering a "daily" entry here once that path is actually needed.
    transport_params = {
        "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    }
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
