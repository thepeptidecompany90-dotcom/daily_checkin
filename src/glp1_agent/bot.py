import os
from datetime import UTC, datetime
from uuid import UUID

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.flows import FlowManager
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
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
    STATE_SERVICES,
)

load_dotenv()


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    settings = Settings()

    # NOTE: real call dispatch should pass patient_id via call/room metadata. Reading it from an
    # env var here is a V1 placeholder — out of scope for this pass (see plan doc).
    patient_id = UUID(os.environ["GLP1_PATIENT_ID"])

    pool = await create_pool(settings.database_url)
    services = Services.build(pool)

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY", ""))
    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY", ""),
        settings=CartesiaTTSService.Settings(voice="71a7ad14-091c-4e8e-a314-022ece01c121"),
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

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        processor_unusable_policy=ProcessorUnusablePolicy.END,
    )
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

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
