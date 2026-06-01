import asyncio
import logging
from importlib import import_module
from typing import Tuple

from backend.app.config import config

try:
    from deepgram import DeepgramClient
    EventType = import_module('deepgram.core.events').EventType
    _DEEPGRAM_IMPORT_ERROR = None
except Exception as e:
    DeepgramClient = None
    EventType = None
    _DEEPGRAM_IMPORT_ERROR = e

logger = logging.getLogger(__name__)


def get_deepgram_stt_status() -> Tuple[bool, str]:
    '''Return Deepgram STT runtime availability for startup logging.'''
    if _DEEPGRAM_IMPORT_ERROR is not None:
        return False, f'dependency import failed: {_DEEPGRAM_IMPORT_ERROR}'
    if not config.DEEPGRAM_API_KEY:
        return False, 'DEEPGRAM_API_KEY is missing'
    return True, 'runtime ready'


class DeepgramStreamService:
    def __init__(self):
        enabled, reason = get_deepgram_stt_status()
        if not enabled:
            raise RuntimeError(f'Deepgram dependency missing: {reason}')

        self.client = DeepgramClient(api_key=config.DEEPGRAM_API_KEY)
        self.connection = None
        self._connection_cm = None
        self._listener_task = None
        self._loop = None
        self._transcript_queue = asyncio.Queue()
        self.final_transcript = ''
        self.confidences = []
        self._is_finished = False
        self._final_event_received = asyncio.Event()

    @property
    def is_stream_active(self):
        return self.connection is not None and not self._is_finished

    async def start(self, encoding=None, sample_rate=None, channels=None):
        '''Initialize Deepgram live connection using SDK v6 client API.'''
        try:
            self.final_transcript = ''
            self.confidences = []
            self._is_finished = False
            self._final_event_received.clear()
            self._loop = asyncio.get_running_loop()
            conn_kwargs = {
                'model': 'nova-2',
                'language': 'en-US',
                'smart_format': 'true',
                'interim_results': 'true',
                'utterance_end_ms': '1000',
                'vad_events': 'true',
                'endpointing': '300',
                'encoding': str(encoding or 'linear16'),
                'sample_rate': str(sample_rate or 16000),
                'channels': str(channels or 1),
            }

            self._connection_cm = self.client.listen.v1.connect(**conn_kwargs)
            self.connection = await asyncio.to_thread(self._connection_cm.__enter__)

            self.connection.on(EventType.OPEN, self._on_open)
            self.connection.on(EventType.MESSAGE, self._on_message)
            self.connection.on(EventType.ERROR, self._on_error)
            self.connection.on(EventType.CLOSE, self._on_close)

            self._listener_task = asyncio.create_task(asyncio.to_thread(self.connection.start_listening))
            logger.info('Deepgram STT stream started')
            return True
        except Exception as e:
            logger.warning('Deepgram STT: DISABLED (%s)', e)
            await self.stop()
            return False

    async def send_audio(self, audio_data: bytes):
        '''Send audio chunk to Deepgram.'''
        if self.connection and not self._is_finished:
            try:
                await asyncio.to_thread(self.connection.send_media, audio_data)
            except Exception as e:
                logger.error('Failed to send audio chunk to Deepgram: %s', e)

    async def get_transcript(self):
        '''Retrieve transcript/speech-start events from queue.'''
        return await self._transcript_queue.get()

    def _get_result(self):
        text = self.final_transcript.strip()
        confidence = sum(self.confidences) / len(self.confidences) if self.confidences else 0.0
        return {'text': text, 'confidence': confidence}

    async def finish(self):
        '''Signal end of stream and wait for final transcript.'''
        if self._is_finished:
            return self._get_result()

        self._is_finished = True
        if self.connection:
            logger.info('Finishing Deepgram stream')
            try:
                # Python SDK uses finish() on connection to send CloseStream and await final replies
                if hasattr(self.connection, 'finish'):
                    await asyncio.to_thread(self.connection.finish)
                else: # fallback
                    await asyncio.to_thread(self.connection.send_close_stream)

                logger.info('waiting for transcript')

                # WAIT for transcript event:
                timeout = 2.0
                start_wait = asyncio.get_running_loop().time()
                while asyncio.get_running_loop().time() - start_wait < timeout:
                    if self.final_transcript.strip():
                        break
                    await asyncio.sleep(0.1)

                logger.info('transcript received')
                return self._get_result()
            except Exception as e:
                logger.warning(f'Deepgram finish warning: {e}')
        return self._get_result()

    async def stop(self):
        '''Close Deepgram stream resources gracefully.'''
        self._is_finished = True
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        if self.connection:
            try:
                await asyncio.to_thread(self.connection.send_close_stream)
            except Exception as e:
                pass

        if self._connection_cm is not None:
            try:
                await asyncio.to_thread(self._connection_cm.__exit__, None, None, None)
            except Exception as e:
                pass

        self.connection = None
        self._connection_cm = None
        logger.info('Deepgram live connection closed')

    def _queue_event(self, payload: dict):
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._transcript_queue.put_nowait, payload)

    def _on_open(self, *args, **kwargs):
        logger.info('Deepgram: connection open')

    def _on_message(self, event):
        if event is None:
            return

        event_name = event.__class__.__name__
        if event_name == 'ListenV1SpeechStarted':
            self._queue_event({'type': 'speech_started'})
            return

        if event_name != 'ListenV1Results':
            return

        channel = getattr(event, 'channel', None)
        alternatives = getattr(channel, 'alternatives', []) if channel else []
        if not alternatives:
            return

        primary_alt = alternatives[0]
        sentence = (getattr(primary_alt, 'transcript', '') or '').strip()
        if not sentence:
            return

        is_final = bool(getattr(event, 'is_final', False))
        confidence = float(getattr(primary_alt, 'confidence', 1.0) or 0.0)

        if is_final:
            self.final_transcript += sentence + ' '
            self.confidences.append(confidence)

        uncertain_words = []
        for word in (getattr(primary_alt, 'words', []) or []):
            word_text = (getattr(word, 'word', '') or '').strip()
            word_conf = float(getattr(word, 'confidence', 1.0) or 0.0)
            if word_text and word_conf < 0.6:
                uncertain_words.append(word_text)

        self._queue_event(
            {
                'type': 'transcript',
                'text': sentence,
                'is_final': is_final,
                'confidence': confidence,
                'uncertain_words': uncertain_words,
            }
        )

    def _on_error(self, error):
        logger.error('Deepgram error: %s', error)

    def _on_close(self, *args, **kwargs):
        logger.info('Deepgram: connection closed')



